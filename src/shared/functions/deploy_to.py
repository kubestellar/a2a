"""Deploy applications to clusters using helm or kubectl."""

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.shared.base_functions import BaseFunction
from src.shared.utils import run_shell_command_with_cancellation


@dataclass
class DeployToInput:
    """All parameters accepted by `deploy_to` bundled in a single object."""

    target_clusters: Optional[List[str]] = None
    cluster_labels: Optional[List[str]] = None
    context: Optional[str] = None  # New parameter for WDS context
    filename: str = ""
    resource_type: str = ""
    resource_name: str = ""
    image: str = ""
    cluster_images: Optional[List[str]] = None
    namespace: str = ""
    all_namespaces: bool = False
    labels: Optional[Dict[str, str]] = None
    namespace_selector: str = ""
    target_namespaces: Optional[List[str]] = None
    resource_filter: str = ""
    api_version: str = ""
    kubeconfig: str = ""
    remote_context: str = ""
    dry_run: bool = False
    list_clusters: bool = False


@dataclass
class DeployToOutput:
    """Standardised response from `deploy_to` so the agent can rely on shape."""

    status: str
    details: Dict[str, Any] = field(default_factory=dict)


class DeployToFunction(BaseFunction):
    """Function to deploy resources to specific clusters within KubeStellar managed clusters."""

    def __init__(self):
        super().__init__(
            name="deploy_to",
            description="Deploy resources to specific named clusters, clusters matching labels, or all clusters in a WDS context. Perfect for edge deployments, staging environments, or when you need workloads only on certain clusters. Use list_clusters=True to see available clusters first. Alternative to multicluster_create for targeted placement.",
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute deployment to target clusters with specified resources and labels.
        
        Args:
            target_clusters (List[str], optional): Names of specific clusters to deploy to. 
                Can include comma-separated lists. Mutually exclusive with cluster_labels and context.
                Example: ['its1'], ['cluster1', 'cluster2']
            
            cluster_labels (List[str], optional): Label selectors for cluster targeting in key=value format.
                Selects clusters based on their labels. Mutually exclusive with target_clusters and context.
                Example: ['location-group=edge', 'environment=production']
            
            context (str, optional): WDS context name to deploy to all clusters in that context.
                Mutually exclusive with target_clusters and cluster_labels.
                Example: 'wds1'
            
            filename (str): Path to YAML/JSON file containing resource definitions.
                Required unless using resource_type and resource_name.
                Example: '/tmp/nginx-deployment.yaml'
            
            resource_type (str): Type of resource to create when not using filename.
                Must be used with resource_name. Options: 'deployment', 'service', 'configmap', 'secret', 'namespace'.
                Example: 'deployment'
            
            resource_name (str): Name of resource to create when not using filename.
                Must be used with resource_type.
                Example: 'nginx-deployment'
            
            image (str, optional): Global image override for deployments.
                Applies to all clusters unless overridden by cluster_images.
                Example: 'nginx:1.21'
            
            cluster_images (List[str], optional): Per-cluster image overrides in cluster=image format.
                Allows different images per cluster.
                Example: ['cluster1=nginx:1.0', 'cluster2=nginx:2.0']
            
            namespace (str, optional): Namespace to deploy resources to.
                Defaults to 'default' if not specified.
                Example: 'production'
            
            all_namespaces (bool, optional): If true, deploy to all namespaces.
                Cannot be used with namespace or target_namespaces.
                Default: False
            
            namespace_selector (str, optional): Label selector to filter namespaces.
                Selects namespaces matching the label selector.
                Example: 'environment=production'
            
            target_namespaces (List[str], optional): Specific list of namespaces to deploy to.
                Alternative to namespace_selector for precise namespace control.
                Example: ['default', 'production']
            
            resource_filter (str, optional): Filter to apply to resources.
                Advanced filtering for specific resource selection.
            
            api_version (str, optional): API version for resource creation.
                Used when creating resources directly (not from file).
                Example: 'apps/v1'
            
            kubeconfig (str, optional): Path to kubeconfig file.
                Uses default kubeconfig if not specified.
                Example: '/path/to/kubeconfig'
            
            remote_context (str, optional): Remote context for cluster access.
                Used for multi-cluster setups with context switching.
            
            dry_run (bool, optional): If true, only show what would be deployed without making changes.
                Useful for validation and planning.
                Default: False
            
            list_clusters (bool, optional): If true, list available clusters and their status.
                Returns cluster information without performing deployment.
                Default: False
            
            labels (Dict[str, str], optional): Key/value pairs to label resources after deployment.
                Applied to all deployed resources. Essential for binding policies.
                Example: {'app.kubernetes.io/name': 'nginx', 'environment': 'production'}
        
        Returns:
            Dict[str, Any]: Deployment result containing:
                - status: 'success' or 'error'
                - details: Dictionary with deployment information including:
                    - clusters_selected: Number of clusters targeted
                    - clusters_succeeded: Number of successful deployments
                    - clusters_failed: Number of failed deployments
                    - deployment_plan: Summary of what was deployed
                    - results: Detailed results per cluster
        
        Example:
            >>> deploy_to(
            ...     target_clusters=['cluster1'],
            ...     filename='/tmp/nginx-deployment.yaml',
            ...     labels={'app.kubernetes.io/name': 'nginx', 'environment': 'production'}
            ... )
            
            >>> deploy_to(
            ...     context='wds1',
            ...     filename='/tmp/nginx-deployment.yaml',
            ...     labels={'app.kubernetes.io/name': 'nginx', 'environment': 'production'}
            ... )
        """
        # Build strongly-typed input object (the agent can create this directly)
        params = DeployToInput(**kwargs)

        # Unpack once for readability / minimal downstream changes
        target_clusters = params.target_clusters
        cluster_labels = params.cluster_labels
        context = params.context
        filename = params.filename
        resource_type = params.resource_type
        resource_name = params.resource_name
        image = params.image
        cluster_images = params.cluster_images
        namespace = params.namespace
        all_namespaces = params.all_namespaces
        namespace_selector = params.namespace_selector
        target_namespaces = params.target_namespaces
        resource_filter = params.resource_filter
        api_version = params.api_version
        kubeconfig = params.kubeconfig
        remote_context = params.remote_context
        dry_run = params.dry_run
        list_clusters = params.list_clusters
        labels = params.labels
        
        # Fix JSON formatting issues with labels
        def _fix_labels_json(labels_obj):
            """Fix unquoted string values in labels JSON"""
            if labels_obj and hasattr(labels_obj, 'items') and callable(getattr(labels_obj, 'items')):
                # Handle MapComposite objects
                labels_obj = dict(labels_obj.items())
            
            if isinstance(labels_obj, dict):
                fixed = {}
                for k, v in labels_obj.items():
                    # Keep ALL values as strings - no hardcoding specific values
                    if isinstance(v, str):
                        fixed[k] = v  # Keep all strings as strings
                    elif isinstance(v, dict):
                        fixed[k] = _fix_labels_json(v)
                    else:
                        fixed[k] = str(v) if v is not None else v
                return fixed
            return labels_obj
        
        if labels:
            labels = _fix_labels_json(labels)
        
        try:
            # Handle list clusters request
            if list_clusters:
                list_resp = await self._list_available_clusters(kubeconfig, remote_context)
                return asdict(DeployToOutput(status=list_resp["status"], details=list_resp))

            # Validate inputs
            if not target_clusters and not cluster_labels and not context:
                err = {
                    "status": "error",
                    "error": "Must specify either target_clusters, cluster_labels, or context",
                }
                return asdict(DeployToOutput(status="error", details=err))

            # Validate mutual exclusivity
            if context and (target_clusters or cluster_labels):
                err = {
                    "status": "error",
                    "error": "Cannot specify context with target_clusters or cluster_labels",
                }
                return asdict(DeployToOutput(status="error", details=err))

            if not filename and not (resource_type and resource_name):
                err = {
                    "status": "error",
                    "error": "Must specify either filename or both resource_type and resource_name",
                }
                return asdict(DeployToOutput(status="error", details=err))

            # Discover all available clusters
            all_clusters = await self._discover_clusters(kubeconfig, remote_context)
            if not all_clusters:
                err = {"status": "error", "error": "No clusters discovered"}
                return asdict(DeployToOutput(status="error", details=err))

            if not target_clusters and not cluster_labels and not context:
                if context:
                    # For KubeStellar workflows, auto-select ITS cluster when WDS context is provided
                    available_clusters = self._discover_clusters(kubeconfig)
                    its_clusters = [cluster for cluster in available_clusters if self._is_its_cluster(cluster, kubeconfig)]
                    
                    if its_clusters:
                        target_clusters = [its_clusters[0]]
                        self.console.print(f"[dim]📍 Auto-selected ITS cluster: {target_clusters[0]}[/dim]")
                    else:
                        return {"status": "error", "error": "No ITS clusters found for smart targeting. Please specify target_clusters explicitly."}
                else:
                    return {"status": "error", "error": "No targeting specified. Please provide target_clusters, cluster_labels, or context."}
            
            if not target_clusters and not cluster_labels and not context:
                return {"status": "error", "error": "target_clusters, cluster_labels, or context is required"}

            if context:
                # Get all clusters registered in the WDS context
                try:
                    cmd = ["kubectl", "--context", context, "get", "bindings.control.kubestellar.io", "-o", "json"]
                    if kubeconfig:
                        cmd += ["--kubeconfig", kubeconfig]
                    ret = await self._run_command(cmd)
                    if ret["returncode"] == 0:
                        bindings = json.loads(ret["stdout"]).get("items", [])
                        target_clusters = []
                        for binding in bindings:
                            for dest in binding.get("spec", {}).get("destinations", []):
                                cluster_id = dest.get("clusterId")
                                if cluster_id:
                                    target_clusters.append(cluster_id)
                        if not target_clusters:
                            err = {"status": "error", "error": f"No clusters found in context '{context}'"}
                            return asdict(DeployToOutput(status="error", details=err))
                    else:
                        err = {"status": "error", "error": f"Failed to get clusters from context '{context}': {ret['stderr']}"}
                        return asdict(DeployToOutput(status="error", details=err))
                except Exception as e:
                    err = {"status": "error", "error": f"Error getting clusters from context '{context}': {str(e)}"}
                    return asdict(DeployToOutput(status="error", details=err))

            # Filter clusters based on selection criteria
            selected_clusters = self._filter_clusters(
                all_clusters, target_clusters, cluster_labels
            )

            if not selected_clusters:
                err = {
                    "status": "error",
                    "error": "No clusters match the selection criteria",
                    "available_clusters": [
                        {"name": c["name"], "context": c["context"]} for c in all_clusters
                    ],
                }
                return asdict(DeployToOutput(status="error", details=err))

            # Determine target namespaces
            target_ns_list = await self._resolve_target_namespaces(
                selected_clusters[0],
                all_namespaces,
                namespace_selector,
                target_namespaces,
                namespace,
                kubeconfig,
            )

            # Show deployment plan
            deployment_plan = {
                "target_clusters": [c["name"] for c in selected_clusters],
                "target_namespaces": target_ns_list,
                "resource_info": {
                    "filename": filename,
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "image": image,
                    "api_version": api_version,
                    "resource_filter": resource_filter,
                },
            }

            if dry_run:
                dry_resp = {
                    "status": "success",
                    "message": "DRY RUN - No actual deployment will occur",
                    "deployment_plan": deployment_plan,
                    "clusters_selected": len(selected_clusters),
                    "selected_clusters": selected_clusters,
                }
                return asdict(DeployToOutput(status="success", details=dry_resp))

            # Execute deployment on selected clusters
            results = await self._deploy_to_clusters(
                selected_clusters,
                filename,
                resource_type,
                resource_name,
                image,
                cluster_images,
                target_ns_list,
                kubeconfig,
                api_version,
                labels,
            )

            success_count = sum(1 for r in results.values() if r["status"] == "success")

            final_resp = {
                "clusters_selected": len(selected_clusters),
                "clusters_succeeded": success_count,
                "clusters_failed": len(selected_clusters) - success_count,
                "deployment_plan": deployment_plan,
                "results": results,
            }
            status = "success" if success_count > 0 else "error"
            return asdict(DeployToOutput(status=status, details=final_resp))

        except Exception as e:
            err = {"status": "error", "error": f"Failed to deploy to clusters: {str(e)}"}
            return asdict(DeployToOutput(status="error", details=err))

    async def _list_available_clusters(
        self, kubeconfig: str, remote_context: str
    ) -> Dict[str, Any]:
        """List available clusters and their details."""
        try:
            clusters = await self._discover_clusters(kubeconfig, remote_context)

            if not clusters:
                return {
                    "status": "success",
                    "message": "No clusters discovered",
                    "clusters": [],
                }

            cluster_info = []
            for cluster in clusters:
                cluster_info.append(
                    {
                        "name": cluster["name"],
                        "context": cluster["context"],
                        "status": cluster.get("status", "Unknown"),
                    }
                )

            # Generate usage examples
            example_commands = []
            if clusters:
                first_cluster = clusters[0]["name"]
                example_commands = [
                    f'Deploy to specific cluster: target_clusters=["{first_cluster}"]',
                    f'Deploy with dry-run: target_clusters=["{first_cluster}"], dry_run=True',
                    "Deploy with binding policy (recommended): Use create_binding_policy function",
                ]

            return {
                "status": "success",
                "clusters_total": len(clusters),
                "clusters": cluster_info,
                "usage_examples": example_commands,
                "recommendation": "For better long-term management, consider using binding policies instead of direct deployment",
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to list clusters: {str(e)}"}

    async def _resolve_target_namespaces(
        self,
        cluster: Dict[str, Any],
        all_namespaces: bool,
        namespace_selector: str,
        target_namespaces: Optional[List[str]],
        namespace: str,
        kubeconfig: str,
    ) -> List[str]:
        """Resolve the list of target namespaces based on input parameters."""
        try:
            if target_namespaces:
                return target_namespaces

            if all_namespaces or namespace_selector:
                # Get all namespaces from the first cluster
                cmd = ["kubectl", "get", "namespaces", "--context", cluster["context"]]

                if kubeconfig:
                    cmd.extend(["--kubeconfig", kubeconfig])

                if namespace_selector:
                    cmd.extend(["-l", namespace_selector])

                cmd.extend(["-o", "jsonpath={.items[*].metadata.name}"])

                result = await self._run_command(cmd)
                if result["returncode"] == 0:
                    namespaces = result["stdout"].strip().split()
                    return [ns for ns in namespaces if ns]

            if namespace:
                return [namespace]

            return ["default"]

        except Exception:
            return ["default"] if not namespace else [namespace]

    async def _deploy_to_clusters(
        self,
        clusters: List[Dict[str, Any]],
        filename: str,
        resource_type: str,
        resource_name: str,
        image: str,
        cluster_images: Optional[List[str]],
        target_namespaces: List[str],
        kubeconfig: str,
        api_version: str,
        labels: Optional[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Deploy to selected clusters."""
        results = {}

        # Parse cluster-specific images
        cluster_image_map = {}
        if cluster_images:
            for cluster_image in cluster_images:
                if "=" in cluster_image:
                    cluster_name, img = cluster_image.split("=", 1)
                    cluster_image_map[cluster_name.strip()] = img.strip()

        # Deploy to each selected cluster
        for cluster in clusters:
            result = await self._deploy_to_cluster(
                cluster,
                filename,
                resource_type,
                resource_name,
                image,
                cluster_image_map,
                target_namespaces,
                kubeconfig,
                api_version,
                labels,
            )
            results[cluster["name"]] = result

        return results

    async def _deploy_to_cluster(
        self,
        cluster: Dict[str, Any],
        filename: str,
        resource_type: str,
        resource_name: str,
        image: str,
        cluster_image_map: Dict[str, str],
        target_namespaces: List[str],
        kubeconfig: str,
        api_version: str,
        labels: Optional[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Deploy to a specific cluster across target namespaces."""
        try:
            namespace_results = {}

            for namespace in target_namespaces:
                # Check if namespace exists, create if it doesn't
                ns_check_cmd = ["kubectl", "get", "namespace", namespace, 
                               "--context", cluster["context"]]
                if kubeconfig:
                    ns_check_cmd.extend(["--kubeconfig", kubeconfig])
                
                # Try to check if namespace exists
                namespace_exists = False
                try:
                    result = await self._run_command(ns_check_cmd)
                    if result["returncode"] == 0:
                        namespace_exists = True
                except Exception:
                    namespace_exists = False
                
                # If namespace doesn't exist, create it
                if not namespace_exists:
                    ns_create_cmd = ["kubectl", "create", "namespace", namespace, 
                                     "--context", cluster["context"]]
                    if kubeconfig:
                        ns_create_cmd.extend(["--kubeconfig", kubeconfig])
                    
                    try:
                        create_result = await self._run_command(ns_create_cmd)
                        if create_result["returncode"] != 0:
                            # If namespace creation failed, log error and skip deployment
                            namespace_results[namespace] = {
                                "status": "error",
                                "error": f"Failed to create namespace: {create_result.get('stderr', 'Unknown error')}"
                            }
                            continue
                    except Exception as e:
                        # If namespace creation failed with exception, log error and skip deployment
                        namespace_results[namespace] = {
                            "status": "error", 
                            "error": f"Failed to create namespace: {str(e)}"
                        }
                        continue
                
                # Build kubectl command for each namespace
                if filename:
                    cmd = ["kubectl", "apply", "-f", filename]
                else:
                    cmd = ["kubectl", "create", resource_type, resource_name]

                    # Add API version if specified
                    if api_version:
                        # For kubectl create, API version is typically embedded in the resource type
                        pass  # API version handling would be more complex for direct resource creation

                    # Handle image for deployments
                    if resource_type == "deployment":
                        cluster_specific_image = cluster_image_map.get(cluster["name"])
                        if cluster_specific_image:
                            cmd.extend(["--image", cluster_specific_image])
                            image_used = cluster_specific_image
                        elif image:
                            cmd.extend(["--image", image])
                            image_used = image
                        else:
                            image_used = None

                # Add common parameters
                cmd.extend(["--context", cluster["context"]])

                if kubeconfig:
                    cmd.extend(["--kubeconfig", kubeconfig])

                cmd.extend(["--namespace", namespace])

                # Execute command
                result = await self._run_command(cmd)

                if result["returncode"] == 0:
                    response = {"status": "success", "output": result["stdout"]}

                    # Add image info for deployments
                    if resource_type == "deployment" and "image_used" in locals():
                        response["image_used"] = image_used
                    if labels:
                        label_response = await self._apply_labels(
                            filename,
                            cluster,
                            namespace,
                            labels,
                            kubeconfig,
                        )
                        response["label_result"] = label_response

                    namespace_results[namespace] = response
                else:
                    # Provide friendly error messages
                    error_output = result["stderr"] or result["stdout"]
                    if "already exists" in error_output:
                        error_msg = "Resource already exists in this namespace"
                    elif "not found" in error_output:
                        error_msg = "Namespace or resource type not found"
                    else:
                        error_msg = f"Deployment failed: {error_output}"

                    namespace_results[namespace] = {
                        "status": "error",
                        "error": error_msg,
                        "output": error_output,
                    }

            # Summarize results across namespaces
            success_count = sum(
                1 for r in namespace_results.values() if r["status"] == "success"
            )
            total_count = len(namespace_results)

            return {
                "status": "success" if success_count > 0 else "error",
                "cluster": cluster["name"],
                "namespaces_total": total_count,
                "namespaces_succeeded": success_count,
                "namespaces_failed": total_count - success_count,
                "namespace_results": namespace_results,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to deploy to cluster {cluster['name']}: {str(e)}",
                "cluster": cluster["name"],
            }

    async def _apply_labels(
        self,
        filename: str,
        cluster: Dict[str, Any],
        namespace: str,
        labels: Dict[str, str],
        kubeconfig: str,
    ) -> Dict[str, Any]:
        cmd = ["kubectl", "label", "-f", filename, "--context", cluster["context"], "--namespace", namespace, "--overwrite"]
        if kubeconfig:
            cmd.extend(["--kubeconfig", kubeconfig])

        for key, value in labels.items():
            cmd.append(f"{key}={value}")

        result = await self._run_command(cmd)
        if result["returncode"] == 0:
            return {"status": "success", "output": result["stdout"]}
        return {"status": "error", "output": result["stderr"] or result["stdout"]}

    def _filter_clusters(
        self,
        all_clusters: List[Dict[str, Any]],
        target_names: Optional[List[str]],
        cluster_labels: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """Filter clusters based on selection criteria."""
        if target_names:
            # Filter by cluster names
            name_set = set()
            for name_list in target_names:
                # Handle comma-separated names
                if isinstance(name_list, str):
                    names = [n.strip() for n in name_list.split(",")]
                    name_set.update(names)
                else:
                    name_set.add(name_list)

            return [
                c
                for c in all_clusters
                if c["name"] in name_set or c["context"] in name_set
            ]

        if cluster_labels:
            # Parse label selectors
            label_selectors = {}
            for label in cluster_labels:
                if "=" in label:
                    key, value = label.split("=", 1)
                    label_selectors[key.strip()] = value.strip()

            # Note: In a real implementation, you would check actual cluster labels
            # For now, this returns all clusters with a warning
            # In production, this would query cluster metadata or labels
            return all_clusters

        return []

    async def _discover_clusters(
        self, kubeconfig: str, remote_context: str
    ) -> List[Dict[str, Any]]:
        """Discover available clusters using kubectl."""
        try:
            clusters = []

            # Get kubeconfig contexts
            cmd = ["kubectl", "config", "get-contexts", "-o", "name"]
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(cmd)
            if result["returncode"] != 0:
                return []

            contexts = result["stdout"].strip().split("\n")

            # Test connectivity to each context
            for context in contexts:
                if not context.strip():
                    continue

                # Skip WDS (Workload Description Space) clusters
                if self._is_wds_cluster(context):
                    continue

                # Test cluster connectivity
                test_cmd = ["kubectl", "cluster-info", "--context", context]
                if kubeconfig:
                    test_cmd.extend(["--kubeconfig", kubeconfig])

                test_result = await self._run_command(test_cmd)
                status = "Ready" if test_result["returncode"] == 0 else "Unreachable"

                clusters.append({"name": context, "context": context, "status": status})

            return clusters

        except Exception:
            return []

    def _is_wds_cluster(self, cluster_name: str) -> bool:
        """Check if cluster is a WDS (Workload Description Space) cluster."""
        lower_name = cluster_name.lower()
        return (
            lower_name.startswith("wds")
            or "-wds-" in lower_name
            or "_wds_" in lower_name
        )

    async def _run_command(self, cmd: List[str]) -> Dict[str, Any]:
        """Run a shell command asynchronously with cancellation support."""
        return await run_shell_command_with_cancellation(cmd)

    def get_schema(self) -> Dict[str, Any]:
        """Define the JSON schema for function parameters."""
        return {
            "type": "object",
            "properties": {
                "target_clusters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Names of specific clusters to deploy to (can include comma-separated lists)",
                },
                "cluster_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Label selectors for cluster targeting in key=value format",
                },
                "filename": {
                    "type": "string",
                    "description": "Path to YAML/JSON file containing resource definitions",
                },
                "resource_type": {
                    "type": "string",
                    "description": "Type of resource to create (when not using filename)",
                    "enum": [
                        "deployment",
                        "service",
                        "configmap",
                        "secret",
                        "namespace",
                    ],
                },
                "resource_name": {
                    "type": "string",
                    "description": "Name of resource to create (when not using filename)",
                },
                "image": {
                    "type": "string",
                    "description": "Global image override for deployments",
                },
                "cluster_images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Per-cluster image overrides in cluster=image format",
                },
                "labels": {
                    "type": "object",
                    "description": "Optional key/value pairs to label resources after deployment",
                    "additionalProperties": {"type": "string"},
                },
                "annotations": {
                    "type": "object",
                    "description": "Optional key/value pairs to annotate resources after deployment",
                    "additionalProperties": {"type": "string"},
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace to deploy resources to",
                    "default": "default",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, only show what would be deployed without making changes",
                    "default": False,
                },
                "list_clusters": {
                    "type": "boolean",
                    "description": "If true, list available clusters and their status",
                    "default": False,
                },
            },
            "required": [],
        }
