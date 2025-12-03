"""Multi-cluster create function for KubeStellar."""

import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.shared.base_functions import BaseFunction


@dataclass
class MultiClusterCreateInput:
    """All parameters accepted by multicluster_create.execute."""

    resource_type: str = ""
    resource_name: str = ""
    filename: str = ""
    image: str = ""
    replicas: int = 1
    port: int = 0
    namespace: str = ""
    all_namespaces: bool = False
    namespace_selector: str = ""
    target_namespaces: Optional[List[str]] = None
    resource_filter: str = ""
    api_version: str = ""
    kubeconfig: str = ""
    remote_context: str = ""
    dry_run: str = "none"
    labels: Optional[Dict[str, str]] = None


@dataclass
class MultiClusterCreateOutput:
    """Uniform envelope returned by multicluster_create."""

    status: str
    details: Dict[str, Any] = field(default_factory=dict)


class MultiClusterCreateFunction(BaseFunction):
    """Function to create resources across multiple Kubernetes clusters."""

    def __init__(self):
        super().__init__(
            name="multicluster_create",
            description="Create and deploy Kubernetes workloads (deployments, services, configmaps) across all clusters simultaneously. Use this for global resource creation that should appear on every cluster in your KubeStellar fleet. For targeted deployment to specific clusters, use deploy_to instead.",
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Create resources across multiple Kubernetes clusters.

        Args:
            filename (str): Path to a YAML/JSON file containing resource definitions.
            resource_type (str): Type of resource to create (e.g., deployment, service). Required if `filename` is empty.
            resource_name (str): Name of the resource to create. Required if `resource_type` is specified.
            image (str): Container image for deployments.
            replicas (int): Number of replicas for deployments (default 1).
            port (int): Port to expose for deployments (default 0).
            namespace (str): Target namespace.
            all_namespaces (bool): Create resources across all namespaces.
            target_namespaces (List[str]): Specific list of namespaces to target.
            dry_run (str): Dry run mode ('none', 'client', 'server').
            labels (Dict[str, str]): Labels to apply to the created resources.
            kubeconfig (str): Path to kubeconfig file.

        Returns:
            Dictionary with creation results from all clusters
        """
        try:

            params = MultiClusterCreateInput(**kwargs)

            resource_type = params.resource_type
            resource_name = params.resource_name
            filename = params.filename
            image = params.image
            replicas = params.replicas
            port = params.port
            namespace = params.namespace
            all_namespaces = params.all_namespaces
            namespace_selector = params.namespace_selector
            target_namespaces = params.target_namespaces
            api_version = params.api_version
            kubeconfig = params.kubeconfig
            remote_context = params.remote_context
            dry_run = params.dry_run
            labels = params.labels

            # Validate inputs
            if not filename and not resource_type:
                err = {
                    "error": "Either filename or resource_type must be specified",
                }
                return asdict(MultiClusterCreateOutput(status="error", details=err))

            if resource_type and not resource_name:
                err = {
                    "error": "resource_name is required when resource_type is specified",
                }
                return asdict(MultiClusterCreateOutput(status="error", details=err))

            # Discover clusters
            clusters = await self._discover_clusters(kubeconfig, remote_context)
            if not clusters:
                err = {"error": "No clusters discovered"}
                return asdict(MultiClusterCreateOutput(status="error", details=err))

            # Show binding policy recommendation for resource creation
            warning_msg: Optional[str] = None
            if resource_type and not filename:
                warning_msg = (
                    "WARNING: Direct resource creation across multiple clusters is not recommended. "
                    "Consider using KubeStellar binding policies for better multi-cluster management."
                )

            # Determine target namespaces if using namespace-aware operations
            target_ns_list = []
            if all_namespaces or namespace_selector or target_namespaces:
                target_ns_list = await self._resolve_target_namespaces(
                    clusters[0],
                    all_namespaces,
                    namespace_selector,
                    target_namespaces,
                    kubeconfig,
                )
            elif namespace:
                target_ns_list = [namespace]
            else:
                target_ns_list = ["default"]

            # Execute create command on all clusters and namespaces
            results = {}
            for cluster in clusters:
                cluster_result = await self._create_on_cluster(
                    cluster,
                    resource_type,
                    resource_name,
                    filename,
                    image,
                    replicas,
                    port,
                    target_ns_list,
                    kubeconfig,
                    dry_run,
                    labels,
                    api_version,
                )
                results[cluster["name"]] = cluster_result

            success_count = sum(1 for r in results.values() if r["status"] == "success")
            total_count = len(results)

            final = {
                "clusters_total": total_count,
                "clusters_succeeded": success_count,
                "clusters_failed": total_count - success_count,
                "results": results,
                "warning": warning_msg,
            }
            status = "success" if success_count > 0 else "error"
            return asdict(MultiClusterCreateOutput(status=status, details=final))

        except Exception as e:
            err = {"error": f"Failed to create resources: {str(e)}"}
            return asdict(MultiClusterCreateOutput(status="error", details=err))

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
                if test_result["returncode"] == 0:
                    clusters.append(
                        {"name": context, "context": context, "status": "Ready"}
                    )

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

    async def _resolve_target_namespaces(
        self,
        cluster: Dict[str, Any],
        all_namespaces: bool,
        namespace_selector: str,
        target_namespaces: Optional[List[str]],
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

            return ["default"]

        except Exception:
            return ["default"]

    async def _create_on_cluster(
        self,
        cluster: Dict[str, Any],
        resource_type: str,
        resource_name: str,
        filename: str,
        image: str,
        replicas: int,
        port: int,
        target_namespaces: List[str],
        kubeconfig: str,
        dry_run: str,
        labels: Optional[Dict[str, str]],
        api_version: str,
    ) -> Dict[str, Any]:
        """Create resource on a specific cluster across target namespaces."""
        try:
            namespace_results = {}

            for namespace in target_namespaces:
                # Build kubectl command for each namespace
                cmd = ["kubectl"]

                if filename:
                    cmd.extend(["apply", "-f", filename])
                else:
                    cmd.extend(["create", resource_type, resource_name])

                    # Add API version if specified
                    if api_version:
                        # For kubectl create, API version is typically embedded in the resource type
                        pass  # API version handling would be more complex for direct resource creation

                    # Add resource-specific parameters
                    if resource_type == "deployment" and image:
                        cmd.extend(["--image", image])
                        if replicas > 1:
                            cmd.extend(["--replicas", str(replicas)])
                        if port > 0:
                            cmd.extend(["--port", str(port)])

                # Add common parameters
                cmd.extend(["--context", cluster["context"]])

                if kubeconfig:
                    cmd.extend(["--kubeconfig", kubeconfig])

                cmd.extend(["--namespace", namespace])

                if dry_run != "none":
                    cmd.extend(["--dry-run", dry_run])

                # Add labels if specified
                if labels:
                    label_strings = [f"{k}={v}" for k, v in labels.items()]
                    for label in label_strings:
                        cmd.extend(["--label", label])

                # Execute command
                result = await self._run_command(cmd)

                if result["returncode"] == 0:
                    namespace_results[namespace] = {
                        "status": "success",
                        "output": result["stdout"],
                    }
                else:
                    # Provide friendly error messages
                    error_output = result["stderr"] or result["stdout"]
                    if "already exists" in error_output:
                        error_msg = "Resource already exists in this namespace"
                    elif "not found" in error_output:
                        error_msg = "Namespace or resource type not found"
                    else:
                        error_msg = f"Creation failed: {error_output}"

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
                "error": f"Failed to create on cluster {cluster['name']}: {str(e)}",
                "cluster": cluster["name"],
            }

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
                "resource_type": {
                    "type": "string",
                    "description": "Type of Kubernetes resource to create (deployment, service, configmap, secret, namespace)",
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
                    "description": "Name of the resource to create",
                },
                "filename": {
                    "type": "string",
                    "description": "Path to YAML/JSON file containing resource definitions",
                },
                "image": {
                    "type": "string",
                    "description": "Container image for deployments",
                },
                "replicas": {
                    "type": "integer",
                    "description": "Number of replicas for deployments",
                    "default": 1,
                    "minimum": 1,
                },
                "port": {
                    "type": "integer",
                    "description": "Port to expose for deployments",
                    "default": 0,
                    "minimum": 0,
                },
                "namespace": {
                    "type": "string",
                    "description": "Target namespace for resource creation (ignored if using all_namespaces or target_namespaces)",
                },
                "all_namespaces": {
                    "type": "boolean",
                    "description": "Create resources across all namespaces",
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
                    "description": "Specific API version to use for resource creation",
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
                    "type": "string",
                    "description": "Dry run mode",
                    "enum": ["none", "client", "server"],
                    "default": "none",
                },
                "labels": {
                    "type": "object",
                    "description": "Labels to apply to the created resources",
                    "additionalProperties": {"type": "string"},
                },
            },
            "anyOf": [
                {"required": ["filename"]},
                {"required": ["resource_type", "resource_name"]},
            ],
        }
