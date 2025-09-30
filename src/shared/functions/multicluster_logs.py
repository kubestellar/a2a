"""Multi-cluster logs function for KubeStellar."""

import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..base_functions import BaseFunction




@dataclass
class MultiClusterLogsInput:
    """Full parameter set accepted by `multicluster_logs`."""

    pod_name: str = ""
    resource_selector: str = ""
    container: str = ""
    follow: bool = False
    previous: bool = False
    tail: int = -1
    since_time: str = ""
    since_seconds: int = 0
    timestamps: bool = False
    label_selector: str = ""
    all_containers: bool = False
    namespace: str = ""
    all_namespaces: bool = False
    namespace_selector: str = ""
    target_namespaces: Optional[List[str]] = None
    resource_types: Optional[List[str]] = None
    api_version: str = ""
    kubeconfig: str = ""
    remote_context: str = ""
    max_log_requests: int = 10


@dataclass
class MultiClusterLogsOutput:
    """Uniform envelope returned to callers."""

    status: str
    details: Dict[str, Any] = field(default_factory=dict)


class MultiClusterLogsFunction(BaseFunction):
    """Function to aggregate logs from containers across multiple Kubernetes clusters."""

    def __init__(self):
        super().__init__(
            name="multicluster_logs",
            description="Retrieve and aggregate container logs from pods across multiple clusters. Use this to troubleshoot applications, monitor workloads, or gather logs from distributed services. Can target specific pods by name, label selectors, or resource types (deployment/nginx). Essential for multi-cluster debugging and observability.",
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Aggregate logs from containers across multiple clusters.

        Args:
            (See MultiClusterLogsInput dataclass for full arguments)

        Returns:
            Dictionary with logs from all clusters
        """
        try:

            params = MultiClusterLogsInput(**kwargs)

            pod_name = params.pod_name
            resource_selector = params.resource_selector
            container = params.container
            follow = params.follow
            previous = params.previous
            tail = params.tail
            since_time = params.since_time
            since_seconds = params.since_seconds
            timestamps = params.timestamps
            label_selector = params.label_selector
            all_containers = params.all_containers
            namespace = params.namespace
            all_namespaces = params.all_namespaces
            namespace_selector = params.namespace_selector
            target_namespaces = params.target_namespaces
            resource_types = params.resource_types
            api_version = params.api_version  # kept for potential future use
            kubeconfig = params.kubeconfig
            remote_context = params.remote_context
            max_log_requests = params.max_log_requests


            if (
                not pod_name
                and not resource_selector
                and not label_selector
                and not all_namespaces
            ):
                err = {
                    "error": "Either pod_name, resource_selector, label_selector, or all_namespaces must be specified",
                }
                return asdict(MultiClusterLogsOutput(status="error", details=err))



            # Discover clusters
            clusters = await self._discover_clusters(kubeconfig, remote_context)
            if not clusters:
                err = {"error": "No clusters discovered"}
                return asdict(MultiClusterLogsOutput(status="error", details=err))

            # Determine target namespaces
            target_ns_list = await self._resolve_target_namespaces(
                clusters[0],
                all_namespaces,
                namespace_selector,
                target_namespaces,
                namespace,
                kubeconfig,
            )

            # For follow mode, we need to handle concurrent streaming
            if follow:
                resp = await self._follow_logs_from_clusters(
                    clusters,
                    pod_name,
                    resource_selector,
                    container,
                    tail,
                    since_time,
                    since_seconds,
                    timestamps,
                    label_selector,
                    all_containers,
                    namespace,
                    kubeconfig,
                    max_log_requests,
                )
                return asdict(
                    MultiClusterLogsOutput(status=resp.get("status", "success"), details=resp)
                )
            else:
                resp = await self._get_logs_from_clusters(
                    clusters,
                    pod_name,
                    resource_selector,
                    container,
                    previous,
                    tail,
                    since_time,
                    since_seconds,
                    timestamps,
                    label_selector,
                    all_containers,
                    namespace,
                    target_ns_list,
                    kubeconfig,
                )
                return asdict(
                    MultiClusterLogsOutput(status=resp.get("status", "success"), details=resp)
                )

        except Exception as e:
            err = {"error": f"Failed to get logs: {str(e)}"}
            return asdict(MultiClusterLogsOutput(status="error", details=err))

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

    async def _get_logs_from_clusters(
        self,
        clusters: List[Dict[str, Any]],
        pod_name: str,
        resource_selector: str,
        container: str,
        previous: bool,
        tail: int,
        since_time: str,
        since_seconds: int,
        timestamps: bool,
        label_selector: str,
        all_containers: bool,
        namespace: str,
        target_namespaces: List[str],
        kubeconfig: str,
    ) -> Dict[str, Any]:
        """Get logs from all clusters sequentially."""
        results = {}

        for cluster in clusters:
            cluster_result = await self._get_logs_from_cluster(
                cluster,
                pod_name,
                resource_selector,
                container,
                previous,
                tail,
                since_time,
                since_seconds,
                timestamps,
                label_selector,
                all_containers,
                namespace,
                kubeconfig,
            )
            results[cluster["name"]] = cluster_result

        # Aggregate results
        total_lines = sum(
            len(r.get("logs", []))
            for r in results.values()
            if r.get("status") == "success"
        )

        success_count = sum(1 for r in results.values() if r.get("status") == "success")

        return {
            "status": "success" if success_count > 0 else "error",
            "clusters_total": len(clusters),
            "clusters_succeeded": success_count,
            "clusters_failed": len(clusters) - success_count,
            "total_log_lines": total_lines,
            "results": results,
        }

    async def _follow_logs_from_clusters(
        self,
        clusters: List[Dict[str, Any]],
        pod_name: str,
        resource_selector: str,
        container: str,
        tail: int,
        since_time: str,
        since_seconds: int,
        timestamps: bool,
        label_selector: str,
        all_containers: bool,
        namespace: str,
        kubeconfig: str,
        max_requests: int,
    ) -> Dict[str, Any]:
        """Follow logs from all clusters concurrently with prefixed output."""
        # Limit concurrent requests to avoid overwhelming the system
        semaphore = asyncio.Semaphore(max_requests)

        async def follow_cluster_logs(cluster):
            async with semaphore:
                return await self._follow_logs_from_cluster(
                    cluster,
                    pod_name,
                    resource_selector,
                    container,
                    tail,
                    since_time,
                    since_seconds,
                    timestamps,
                    label_selector,
                    all_containers,
                    namespace,
                    kubeconfig,
                )

        # Start following logs from all clusters concurrently
        tasks = [follow_cluster_logs(cluster) for cluster in clusters]

        try:
            # Wait for all tasks (this will keep running until interrupted)
            results = await asyncio.gather(*tasks, return_exceptions=True)

            success_count = sum(
                1
                for r in results
                if isinstance(r, dict) and r.get("status") == "success"
            )

            return {
                "status": "success" if success_count > 0 else "error",
                "clusters_total": len(clusters),
                "clusters_succeeded": success_count,
                "message": "Log following completed",
                "note": "This operation streams logs continuously until interrupted",
            }

        except asyncio.CancelledError:
            return {"status": "cancelled", "message": "Log following was cancelled"}

    async def _get_logs_from_cluster(
        self,
        cluster: Dict[str, Any],
        pod_name: str,
        resource_selector: str,
        container: str,
        previous: bool,
        tail: int,
        since_time: str,
        since_seconds: int,
        timestamps: bool,
        label_selector: str,
        all_containers: bool,
        namespace: str,
        kubeconfig: str,
    ) -> Dict[str, Any]:
        """Get logs from a specific cluster."""
        try:
            # Build kubectl logs command
            cmd = ["kubectl", "logs", "--context", cluster["context"]]

            # Add resource identifier
            if pod_name:
                cmd.append(pod_name)
            elif resource_selector:
                cmd.append(resource_selector)

            # Add flags
            if container:
                cmd.extend(["-c", container])
            if previous:
                cmd.append("-p")
            if all_containers:
                cmd.append("--all-containers=true")
            if tail >= 0:
                cmd.extend(["--tail", str(tail)])
            if since_time:
                cmd.extend(["--since-time", since_time])
            if since_seconds > 0:
                cmd.extend(["--since", f"{since_seconds}s"])
            if timestamps:
                cmd.append("--timestamps=true")
            if label_selector:
                cmd.extend(["-l", label_selector])
            if namespace:
                cmd.extend(["-n", namespace])
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            # Execute command
            result = await self._run_command(cmd)

            if result["returncode"] == 0:
                logs = (
                    result["stdout"].strip().split("\n")
                    if result["stdout"].strip()
                    else []
                )
                return {
                    "status": "success",
                    "logs": logs,
                    "cluster": cluster["name"],
                    "log_count": len(logs),
                }
            else:
                return {
                    "status": "error",
                    "error": result["stderr"] or "Failed to get logs",
                    "cluster": cluster["name"],
                }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get logs from cluster {cluster['name']}: {str(e)}",
                "cluster": cluster["name"],
            }

    async def _follow_logs_from_cluster(
        self,
        cluster: Dict[str, Any],
        pod_name: str,
        resource_selector: str,
        container: str,
        tail: int,
        since_time: str,
        since_seconds: int,
        timestamps: bool,
        label_selector: str,
        all_containers: bool,
        namespace: str,
        kubeconfig: str,
    ) -> Dict[str, Any]:
        """Follow logs from a specific cluster with real-time streaming."""
        try:
            # Build kubectl logs command with follow flag
            cmd = ["kubectl", "logs", "--context", cluster["context"], "-f"]

            # Add resource identifier
            if pod_name:
                cmd.append(pod_name)
            elif resource_selector:
                cmd.append(resource_selector)

            # Add flags
            if container:
                cmd.extend(["-c", container])
            if all_containers:
                cmd.append("--all-containers=true")
            if tail >= 0:
                cmd.extend(["--tail", str(tail)])
            if since_time:
                cmd.extend(["--since-time", since_time])
            if since_seconds > 0:
                cmd.extend(["--since", f"{since_seconds}s"])
            if timestamps:
                cmd.append("--timestamps=true")
            if label_selector:
                cmd.extend(["-l", label_selector])
            if namespace:
                cmd.extend(["-n", namespace])
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            # Start the process for streaming
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            # Stream output with cluster prefix
            lines_processed = 0
            async for line in self._stream_output(process.stdout, cluster["name"]):
                lines_processed += 1
                # In a real implementation, you'd yield or emit these lines
                # For now, we'll just count them

            await process.wait()

            return {
                "status": "success",
                "cluster": cluster["name"],
                "lines_streamed": lines_processed,
                "message": f"Finished streaming logs from {cluster['name']}",
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to follow logs from cluster {cluster['name']}: {str(e)}",
                "cluster": cluster["name"],
            }

    async def _stream_output(self, stdout, cluster_name: str):
        """Stream output lines with cluster prefix."""
        while True:
            line = await stdout.readline()
            if not line:
                break
            decoded_line = line.decode().rstrip()
            prefixed_line = f"[{cluster_name}] {decoded_line}"
            yield prefixed_line

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
                "pod_name": {
                    "type": "string",
                    "description": "Name of the pod to get logs from",
                },
                "resource_selector": {
                    "type": "string",
                    "description": "Resource selector in TYPE/NAME format (e.g., deployment/nginx)",
                },
                "container": {
                    "type": "string",
                    "description": "Container name to get logs from",
                },
                "follow": {
                    "type": "boolean",
                    "description": "Stream logs continuously",
                    "default": False,
                },
                "previous": {
                    "type": "boolean",
                    "description": "Get logs from previous terminated container",
                    "default": False,
                },
                "tail": {
                    "type": "integer",
                    "description": "Number of recent log lines to display (-1 for all)",
                    "default": -1,
                    "minimum": -1,
                },
                "since_time": {
                    "type": "string",
                    "description": "Only return logs after specific date (RFC3339 format)",
                },
                "since_seconds": {
                    "type": "integer",
                    "description": "Only return logs newer than relative duration in seconds",
                    "default": 0,
                    "minimum": 0,
                },
                "timestamps": {
                    "type": "boolean",
                    "description": "Include timestamps on each line",
                    "default": False,
                },
                "label_selector": {
                    "type": "string",
                    "description": "Label selector to filter pods (e.g., app=nginx)",
                },
                "all_containers": {
                    "type": "boolean",
                    "description": "Get logs from all containers in the pod(s)",
                    "default": False,
                },
                "namespace": {
                    "type": "string",
                    "description": "Target namespace (ignored if using all_namespaces or target_namespaces)",
                },
                "all_namespaces": {
                    "type": "boolean",
                    "description": "Get logs from pods across all namespaces",
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
                "resource_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by specific resource types for GVRC discovery",
                },
                "api_version": {
                    "type": "string",
                    "description": "Specific API version for resource discovery",
                },
                "kubeconfig": {
                    "type": "string",
                    "description": "Path to kubeconfig file",
                },
                "remote_context": {
                    "type": "string",
                    "description": "Remote context for KubeStellar cluster discovery",
                },
                "max_log_requests": {
                    "type": "integer",
                    "description": "Maximum number of concurrent log requests",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "anyOf": [
                {"required": ["pod_name"]},
                {"required": ["resource_selector"]},
                {"required": ["label_selector"]},
            ],
        }