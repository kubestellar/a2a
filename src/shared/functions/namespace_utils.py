"""Namespace management utilities for multi-cluster operations."""

import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.shared.base_functions import BaseFunction


@dataclass
class NamespaceResource:
    """Resource within a namespace."""

    name: str
    kind: str
    api_version: str
    namespace: str
    cluster: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    created: str




@dataclass
class NamespaceUtilsInput:
    """All parameters accepted by namespace_utils.execute in one bundle."""

    operation: str = "list"
    namespace_names: Optional[List[str]] = None
    all_namespaces: bool = False
    namespace_selector: str = ""
    label_selector: str = ""
    resource_types: Optional[List[str]] = None
    include_resources: bool = False
    resource_name: str = ""
    kubeconfig: str = ""
    remote_context: str = ""
    output_format: str = "table"


@dataclass
class NamespaceUtilsOutput:
    """Standardised response returned to the agent."""

    status: str
    details: Dict[str, Any] = field(default_factory=dict)


class NamespaceUtilsFunction(BaseFunction):
    """Function to manage and discover namespace-related operations across clusters."""

    def __init__(self):
        super().__init__(
            name="namespace_utils",
            description="List and count pods, services, deployments and other resources across namespaces and clusters. Use operation='list' to get pod counts and resource information.",
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute namespace utility operations.

        Args:
            operation: Operation to perform (list, get, create, delete, list-resources)
            namespace_names: Specific namespace names to operate on
            all_namespaces: Include all namespaces
            namespace_selector: Namespace label selector
            label_selector: Resource label selector within namespaces
            resource_types: Specific resource types to include
            include_resources: Include resources within namespaces
            kubeconfig: Path to kubeconfig file
            remote_context: Remote context for cluster discovery
            output_format: Output format (table, json, yaml)

        Returns:
            Dictionary with namespace operation results
        """
        try:

            params = NamespaceUtilsInput(**kwargs)

            operation = params.operation
            namespace_names = params.namespace_names
            all_namespaces = params.all_namespaces
            namespace_selector = params.namespace_selector
            label_selector = params.label_selector
            resource_types = params.resource_types
            include_resources = params.include_resources
            resource_name = params.resource_name
            kubeconfig = params.kubeconfig
            remote_context = params.remote_context
            output_format = params.output_format


            # Discover clusters
            clusters = await self._discover_clusters(kubeconfig, remote_context)
            if not clusters:
                return {"status": "error", "error": "No clusters discovered"}

            # Execute operation across clusters
            results = {}
            for cluster in clusters:
                cluster_result = await self._execute_namespace_operation(
                    cluster,
                    operation,
                    namespace_names,
                    all_namespaces,
                    namespace_selector,
                    label_selector,
                    resource_types,
                    include_resources,
                    resource_name,
                    kubeconfig,
                    output_format,
                )
                results[cluster["name"]] = cluster_result

            # Aggregate results
            success_count = sum(1 for r in results.values() if r["status"] == "success")

            final = {
                "operation": operation,
                "clusters_total": len(clusters),
                "clusters_succeeded": success_count,
                "clusters_failed": len(clusters) - success_count,
                "results": results,
            }
            status = "success" if success_count > 0 else "error"
            return asdict(NamespaceUtilsOutput(status=status, details=final))

        except Exception as e:
            err = {"error": f"Failed to execute namespace operation: {str(e)}"}
            return asdict(NamespaceUtilsOutput(status="error", details=err))

    async def _execute_namespace_operation(
        self,
        cluster: Dict[str, Any],
        operation: str,
        namespace_names: Optional[List[str]],
        all_namespaces: bool,
        namespace_selector: str,
        label_selector: str,
        resource_types: Optional[List[str]],
        include_resources: bool,
        resource_name: str,
        kubeconfig: str,
        output_format: str,
    ) -> Dict[str, Any]:
        """Execute namespace operation on a specific cluster."""
        try:
            if operation == "list":
                return await self._list_namespaces(
                    cluster,
                    namespace_names,
                    all_namespaces,
                    namespace_selector,
                    include_resources,
                    resource_types,
                    label_selector,
                    resource_name,
                    kubeconfig,
                )
            elif operation == "get":
                return await self._get_namespace_details(
                    cluster, namespace_names, kubeconfig
                )
            elif operation == "list-resources":
                return await self._list_namespace_resources(
                    cluster,
                    namespace_names,
                    all_namespaces,
                    resource_types,
                    label_selector,
                    resource_name,
                    kubeconfig,
                )
            else:
                return {
                    "status": "error",
                    "error": f"Unsupported operation: {operation}",
                    "cluster": cluster["name"],
                }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed operation on cluster {cluster['name']}: {str(e)}",
                "cluster": cluster["name"],
            }

    async def _list_namespaces(
        self,
        cluster: Dict[str, Any],
        namespace_names: Optional[List[str]],
        all_namespaces: bool,
        namespace_selector: str,
        include_resources: bool,
        resource_types: Optional[List[str]],
        label_selector: str,
        resource_name: str,
        kubeconfig: str,
    ) -> Dict[str, Any]:
        """List namespaces in a cluster."""
        try:
            # Build kubectl command
            cmd = ["kubectl", "get", "namespaces", "--context", cluster["context"]]

            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            # Add namespace selector if specified
            if namespace_selector:
                cmd.extend(["-l", namespace_selector])

            # Add output format
            cmd.extend(["-o", "json"])

            result = await self._run_command(cmd)
            if result["returncode"] != 0:
                return {
                    "status": "error",
                    "error": result["stderr"],
                    "cluster": cluster["name"],
                }

            # Parse JSON output
            import json

            namespace_data = json.loads(result["stdout"])

            namespaces = []
            for ns_item in namespace_data.get("items", []):
                ns_name = ns_item["metadata"]["name"]

                # Filter by namespace names if specified
                if namespace_names and ns_name not in namespace_names:
                    continue

                namespace_info = {
                    "name": ns_name,
                    "status": ns_item["status"]["phase"],
                    "labels": ns_item["metadata"].get("labels", {}),
                    "annotations": ns_item["metadata"].get("annotations", {}),
                    "created": ns_item["metadata"]["creationTimestamp"],
                    "cluster": cluster["name"],
                }

                # Include resources if requested
                if include_resources:
                    resources = await self._get_namespace_resources(
                        cluster, ns_name, resource_types, label_selector, resource_name, kubeconfig
                    )
                    namespace_info["resources"] = resources

                namespaces.append(namespace_info)

            return {
                "status": "success",
                "cluster": cluster["name"],
                "namespaces": namespaces,
                "namespace_count": len(namespaces),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to list namespaces: {str(e)}",
                "cluster": cluster["name"],
            }

    async def _get_namespace_details(
        self,
        cluster: Dict[str, Any],
        namespace_names: Optional[List[str]],
        kubeconfig: str,
    ) -> Dict[str, Any]:
        """Get detailed information for specific namespaces."""
        try:
            if not namespace_names:
                return {
                    "status": "error",
                    "error": "namespace_names required for get operation",
                    "cluster": cluster["name"],
                }

            namespace_details = []
            for ns_name in namespace_names:
                cmd = [
                    "kubectl",
                    "get",
                    "namespace",
                    ns_name,
                    "--context",
                    cluster["context"],
                    "-o",
                    "json",
                ]

                if kubeconfig:
                    cmd.extend(["--kubeconfig", kubeconfig])

                result = await self._run_command(cmd)
                if result["returncode"] == 0:
                    import json

                    ns_data = json.loads(result["stdout"])

                    # Get resource quotas and limits
                    quotas = await self._get_resource_quotas(
                        cluster, ns_name, kubeconfig
                    )
                    limits = await self._get_limit_ranges(cluster, ns_name, kubeconfig)

                    namespace_details.append(
                        {
                            "name": ns_name,
                            "status": ns_data["status"]["phase"],
                            "labels": ns_data["metadata"].get("labels", {}),
                            "annotations": ns_data["metadata"].get("annotations", {}),
                            "created": ns_data["metadata"]["creationTimestamp"],
                            "resource_quotas": quotas,
                            "limit_ranges": limits,
                            "cluster": cluster["name"],
                        }
                    )
                else:
                    namespace_details.append(
                        {
                            "name": ns_name,
                            "error": f"Namespace not found or inaccessible: {result['stderr']}",
                            "cluster": cluster["name"],
                        }
                    )

            return {
                "status": "success",
                "cluster": cluster["name"],
                "namespace_details": namespace_details,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get namespace details: {str(e)}",
                "cluster": cluster["name"],
            }

    async def _list_namespace_resources(
        self,
        cluster: Dict[str, Any],
        namespace_names: Optional[List[str]],
        all_namespaces: bool,
        resource_types: Optional[List[str]],
        label_selector: str,
        resource_name: str,
        kubeconfig: str,
    ) -> Dict[str, Any]:
        """List resources within namespaces."""
        try:
            resources = []

            # Determine which namespaces to query
            target_namespaces = []
            if all_namespaces:
                # Get all namespaces
                ns_result = await self._list_namespaces(
                    cluster, None, True, "", False, None, "", "", kubeconfig
                )
                if ns_result["status"] == "success":
                    target_namespaces = [ns["name"] for ns in ns_result["namespaces"]]
            elif namespace_names:
                target_namespaces = namespace_names
            else:
                target_namespaces = ["default"]

            # Get resources from each namespace
            for namespace in target_namespaces:
                ns_resources = await self._get_namespace_resources(
                    cluster, namespace, resource_types, label_selector, resource_name, kubeconfig
                )
                resources.extend(ns_resources)

            return {
                "status": "success",
                "cluster": cluster["name"],
                "resources": resources,
                "resource_count": len(resources),
                "namespaces_queried": target_namespaces,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to list namespace resources: {str(e)}",
                "cluster": cluster["name"],
            }

    async def _get_namespace_resources(
        self,
        cluster: Dict[str, Any],
        namespace: str,
        resource_types: Optional[List[str]],
        label_selector: str,
        resource_name: str,
        kubeconfig: str,
    ) -> List[Dict[str, Any]]:
        """Get resources within a specific namespace."""
        try:
            resources = []

            # Default resource types if not specified
            if not resource_types:
                resource_types = [
                    "pods",
                    "services",
                    "deployments",
                    "replicasets",
                    "configmaps",
                    "secrets",
                    "persistentvolumeclaims",
                    "ingresses",
                    "jobs",
                    "cronjobs",
                ]

            for resource_type in resource_types:
                cmd = [
                    "kubectl",
                    "get",
                    resource_type,
                    "--namespace",
                    namespace,
                    "--context",
                    cluster["context"],
                ]

                if kubeconfig:
                    cmd.extend(["--kubeconfig", kubeconfig])

                if label_selector:
                    cmd.extend(["-l", label_selector])
                
                if resource_name:
                    cmd.append(resource_name)
                else:
                    cmd.extend(["-o", "json"])

                result = await self._run_command(cmd)
                if result["returncode"] == 0:
                    import json

                    resource_data = json.loads(result["stdout"])

                    for item in resource_data.get("items", []):
                        resources.append(
                            {
                                "name": item["metadata"]["name"],
                                "kind": item["kind"],
                                "api_version": item["apiVersion"],
                                "namespace": namespace,
                                "cluster": cluster["name"],
                                "labels": item["metadata"].get("labels", {}),
                                "annotations": item["metadata"].get("annotations", {}),
                                "created": item["metadata"]["creationTimestamp"],
                            }
                        )

            return resources

        except Exception:
            return []

    async def _get_resource_quotas(
        self, cluster: Dict[str, Any], namespace: str, kubeconfig: str
    ) -> List[Dict[str, Any]]:
        """Get resource quotas for a namespace."""
        try:
            cmd = [
                "kubectl",
                "get",
                "resourcequotas",
                "--namespace",
                namespace,
                "--context",
                cluster["context"],
                "-o",
                "json",
            ]

            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(cmd)
            if result["returncode"] == 0:
                import json

                quota_data = json.loads(result["stdout"])
                return quota_data.get("items", [])
            return []

        except Exception:
            return []

    async def _get_limit_ranges(
        self, cluster: Dict[str, Any], namespace: str, kubeconfig: str
    ) -> List[Dict[str, Any]]:
        """Get limit ranges for a namespace."""
        try:
            cmd = [
                "kubectl",
                "get",
                "limitranges",
                "--namespace",
                namespace,
                "--context",
                cluster["context"],
                "-o",
                "json",
            ]

            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(cmd)
            if result["returncode"] == 0:
                import json

                limit_data = json.loads(result["stdout"])
                return limit_data.get("items", [])
            return []

        except Exception:
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
                "operation": {
                    "type": "string",
                    "description": "Operation to perform",
                    "enum": ["list", "get", "list-resources"],
                    "default": "list",
                },
                "namespace_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific namespace names to operate on",
                },
                "all_namespaces": {
                    "type": "boolean",
                    "description": "Include all namespaces",
                    "default": False,
                },
                "namespace_selector": {
                    "type": "string",
                    "description": "Namespace label selector (e.g., 'env=prod')",
                },
                "label_selector": {
                    "type": "string",
                    "description": "Resource label selector within namespaces",
                },
                "resource_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific resource types to include (pods, services, deployments, etc.)",
                },
                "include_resources": {
                    "type": "boolean",
                    "description": "Include resources within namespaces when listing",
                    "default": False,
                },
                "resource_name": {
                    "type": "string",
                    "description": "Name of the resource to filter by",
                },
                "kubeconfig": {
                    "type": "string",
                    "description": "Path to kubeconfig file",
                },
                "remote_context": {
                    "type": "string",
                    "description": "Remote context for KubeStellar cluster discovery",
                },
                "output_format": {
                    "type": "string",
                    "description": "Output format for results",
                    "enum": ["table", "json", "yaml"],
                    "default": "table",
                },
            },
            "required": [],
        }