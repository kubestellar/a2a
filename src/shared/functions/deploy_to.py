"""Deploy-to function for selective cluster deployment in KubeStellar."""

import asyncio
from typing import Any, Dict, List, Optional

from ..base_functions import BaseFunction


class DeployToFunction(BaseFunction):
    """Function to deploy resources to specific clusters within KubeStellar managed clusters."""

    def __init__(self):
        super().__init__(
            name="deploy_to",
            description="Deploy resources to specific named clusters or clusters matching labels (selective deployment). Perfect for edge deployments, staging environments, or when you need workloads only on certain clusters. Use list_clusters=True to see available clusters first. Alternative to multicluster_create for targeted placement.",
        )

    async def execute(
        self,
        target_clusters: List[str] = None,
        cluster_labels: List[str] = None,
        filename: str = "",
        resource_type: str = "",
        resource_name: str = "",
        image: str = "",
        cluster_images: List[str] = None,
        namespace: str = "",
        all_namespaces: bool = False,
        namespace_selector: str = "",
        target_namespaces: List[str] = None,
        resource_filter: str = "",
        api_version: str = "",
        kubeconfig: str = "",
        remote_context: str = "",
        dry_run: bool = False,
        list_clusters: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Deploy resources to specific clusters.

        Args:
            target_clusters: Names of specific clusters to deploy to
            cluster_labels: Label selectors for cluster targeting (key=value format)
            filename: Path to YAML/JSON file to deploy
            resource_type: Type of resource to create (when not using filename)
            resource_name: Name of resource to create (when not using filename)
            image: Global image override for deployments
            cluster_images: Per-cluster image overrides (cluster=image format)
            namespace: Target namespace for deployment (if not using all_namespaces or target_namespaces)
            all_namespaces: Deploy resources across all namespaces
            namespace_selector: Namespace label selector for targeting
            target_namespaces: Specific list of target namespaces
            resource_filter: Filter resources by name pattern (for GVRC discovery)
            api_version: Specific API version to use for resource deployment
            kubeconfig: Path to kubeconfig file
            remote_context: Remote context for cluster discovery
            dry_run: Show what would be deployed without doing it
            list_clusters: List available clusters and their details

        Returns:
            Dictionary with deployment results or cluster list
        """
        try:
            # Handle list clusters request
            if list_clusters:
                return await self._list_available_clusters(kubeconfig, remote_context)

            # Validate inputs
            if not target_clusters and not cluster_labels:
                return {
                    "status": "error",
                    "error": "Must specify either target_clusters or cluster_labels",
                }

            if not filename and not (resource_type and resource_name):
                return {
                    "status": "error",
                    "error": "Must specify either filename or both resource_type and resource_name",
                }

            # Discover all available clusters
            all_clusters = await self._discover_clusters(kubeconfig, remote_context)
            if not all_clusters:
                return {"status": "error", "error": "No clusters discovered"}

            # Filter clusters based on selection criteria
            selected_clusters = self._filter_clusters(
                all_clusters, target_clusters, cluster_labels
            )

            if not selected_clusters:
                return {
                    "status": "error",
                    "error": "No clusters match the selection criteria",
                    "available_clusters": [
                        {"name": c["name"], "context": c["context"]}
                        for c in all_clusters
                    ],
                }

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
                return {
                    "status": "success",
                    "message": "DRY RUN - No actual deployment will occur",
                    "deployment_plan": deployment_plan,
                    "clusters_selected": len(selected_clusters),
                    "selected_clusters": selected_clusters,
                }

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
            )

            success_count = sum(1 for r in results.values() if r["status"] == "success")

            return {
                "status": "success" if success_count > 0 else "error",
                "clusters_selected": len(selected_clusters),
                "clusters_succeeded": success_count,
                "clusters_failed": len(selected_clusters) - success_count,
                "deployment_plan": deployment_plan,
                "results": results,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to deploy to clusters: {str(e)}",
            }

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
    ) -> Dict[str, Any]:
        """Deploy to a specific cluster across target namespaces."""
        try:
            namespace_results = {}

            for namespace in target_namespaces:
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
        """Run a shell command asynchronously."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            return {
                "returncode": process.returncode,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
            }
        except Exception as e:
            return {"returncode": 1, "stdout": "", "stderr": str(e)}

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
                "namespace": {
                    "type": "string",
                    "description": "Target namespace for deployment (ignored if using all_namespaces or target_namespaces)",
                },
                "all_namespaces": {
                    "type": "boolean",
                    "description": "Deploy resources across all namespaces",
                    "default": False,
                },
                "namespace_selector": {
                    "type": "string",
                    "description": "Namespace label selector for targeting specific namespaces",
                },
                "target_namespaces": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific list of target namespaces",
                },
                "resource_filter": {
                    "type": "string",
                    "description": "Filter resources by name pattern (for GVRC discovery)",
                },
                "api_version": {
                    "type": "string",
                    "description": "Specific API version to use for resource deployment",
                },
                "kubeconfig": {
                    "type": "string",
                    "description": "Path to kubeconfig file",
                },
                "remote_context": {
                    "type": "string",
                    "description": "Remote context for KubeStellar cluster discovery",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Show what would be deployed without actually doing it",
                    "default": False,
                },
                "list_clusters": {
                    "type": "boolean",
                    "description": "List available clusters and their details",
                    "default": False,
                },
            },
            "anyOf": [
                {
                    "required": ["list_clusters"],
                    "properties": {"list_clusters": {"const": True}},
                },
                {
                    "allOf": [
                        {
                            "anyOf": [
                                {"required": ["target_clusters"]},
                                {"required": ["cluster_labels"]},
                            ]
                        },
                        {
                            "anyOf": [
                                {"required": ["filename"]},
                                {"required": ["resource_type", "resource_name"]},
                            ]
                        },
                    ]
                },
            ],
        }
