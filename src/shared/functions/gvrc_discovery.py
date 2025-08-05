"""GVRC (Group, Version, Resource, Category) discovery utilities for KubeStellar."""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..base_functions import BaseFunction


@dataclass
class ResourceInfo:
    """Resource information structure."""

    name: str
    shortnames: List[str]
    api_version: str
    kind: str
    namespaced: bool
    categories: List[str]


@dataclass
class NamespaceInfo:
    """Namespace information structure."""

    name: str
    status: str
    labels: Dict[str, str]
    annotations: Dict[str, str]


class GVRCDiscoveryFunction(BaseFunction):
    """Function to discover Group, Version, Resource, Category information across clusters."""

    def __init__(self):
        super().__init__(
            name="gvrc_discovery",
            description="Discover and inventory all available Kubernetes API resources (pods, services, CRDs, etc.) across clusters. Shows Group/Version/Resource/Category (GVRC) information, API versions, and resource capabilities. Use this to understand what resources are available in your clusters, find custom resources, or check API compatibility across your fleet.",
        )

    async def execute(
        self,
        resource_filter: str = "",
        namespace_filter: str = "",
        all_namespaces: bool = False,
        api_resources: bool = True,
        custom_resources: bool = True,
        categories: List[str] = None,
        kubeconfig: str = "",
        remote_context: str = "",
        output_format: str = "summary",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Discover GVRC information across clusters.

        Args:
            resource_filter: Filter resources by name pattern
            namespace_filter: Filter namespaces by name pattern
            all_namespaces: Discover resources across all namespaces
            api_resources: Include built-in API resources
            custom_resources: Include custom resources (CRDs)
            categories: Filter by resource categories
            kubeconfig: Path to kubeconfig file
            remote_context: Remote context for cluster discovery
            output_format: Output format (summary, detailed, json)

        Returns:
            Dictionary with GVRC discovery results from all clusters
        """
        try:
            # Discover clusters
            clusters = await self._discover_clusters(kubeconfig, remote_context)
            if not clusters:
                return {"status": "error", "error": "No clusters discovered"}

            # Discover resources and namespaces across all clusters
            results = {}
            for cluster in clusters:
                cluster_result = await self._discover_cluster_gvrc(
                    cluster,
                    resource_filter,
                    namespace_filter,
                    all_namespaces,
                    api_resources,
                    custom_resources,
                    categories,
                    kubeconfig,
                    output_format,
                )
                results[cluster["name"]] = cluster_result

            # Aggregate results
            success_count = sum(1 for r in results.values() if r["status"] == "success")

            # Create summary
            if output_format == "summary":
                summary = self._create_summary(results)
            else:
                summary = results

            return {
                "status": "success" if success_count > 0 else "error",
                "clusters_total": len(clusters),
                "clusters_succeeded": success_count,
                "clusters_failed": len(clusters) - success_count,
                "discovery_results": summary,
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to discover GVRC: {str(e)}"}

    async def _discover_cluster_gvrc(
        self,
        cluster: Dict[str, Any],
        resource_filter: str,
        namespace_filter: str,
        all_namespaces: bool,
        api_resources: bool,
        custom_resources: bool,
        categories: Optional[List[str]],
        kubeconfig: str,
        output_format: str,
    ) -> Dict[str, Any]:
        """Discover GVRC information for a specific cluster."""
        try:
            result = {
                "status": "success",
                "cluster": cluster["name"],
                "resources": [],
                "namespaces": [],
                "resource_count": 0,
                "namespace_count": 0,
            }

            # Discover API resources
            if api_resources or custom_resources:
                resources = await self._get_api_resources(
                    cluster, resource_filter, categories, kubeconfig
                )
                result["resources"] = resources
                result["resource_count"] = len(resources)

            # Discover namespaces
            if all_namespaces or namespace_filter:
                namespaces = await self._get_namespaces(
                    cluster, namespace_filter, kubeconfig
                )
                result["namespaces"] = namespaces
                result["namespace_count"] = len(namespaces)

            return result

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to discover GVRC for cluster {cluster['name']}: {str(e)}",
                "cluster": cluster["name"],
            }

    async def _get_api_resources(
        self,
        cluster: Dict[str, Any],
        resource_filter: str,
        categories: Optional[List[str]],
        kubeconfig: str,
    ) -> List[Dict[str, Any]]:
        """Get API resources from a cluster."""
        try:
            # Build kubectl api-resources command
            cmd = ["kubectl", "api-resources", "--context", cluster["context"]]

            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            # Add output format for parsing
            cmd.extend(["-o", "wide"])

            result = await self._run_command(cmd)
            if result["returncode"] != 0:
                return []

            # Parse api-resources output
            resources = []
            lines = result["stdout"].strip().split("\n")

            # Skip header line
            if lines and "NAME" in lines[0]:
                lines = lines[1:]

            for line in lines:
                if not line.strip():
                    continue

                parts = line.split()
                if len(parts) < 4:
                    continue

                resource_name = parts[0]
                shortnames = (
                    parts[1].split(",") if parts[1] not in ["<none>", ""] else []
                )
                api_version = parts[2]
                namespaced = parts[3].upper() == "TRUE"
                kind = parts[4] if len(parts) > 4 else ""
                resource_categories = (
                    parts[5].split(",")
                    if len(parts) > 5 and parts[5] not in ["<none>", ""]
                    else []
                )

                # Apply filters
                if (
                    resource_filter
                    and resource_filter.lower() not in resource_name.lower()
                ):
                    continue

                if categories:
                    if not any(cat in resource_categories for cat in categories):
                        continue

                resources.append(
                    {
                        "name": resource_name,
                        "shortnames": shortnames,
                        "api_version": api_version,
                        "kind": kind,
                        "namespaced": namespaced,
                        "categories": resource_categories,
                    }
                )

            return resources

        except Exception:
            return []

    async def _get_namespaces(
        self, cluster: Dict[str, Any], namespace_filter: str, kubeconfig: str
    ) -> List[Dict[str, Any]]:
        """Get namespaces from a cluster."""
        try:
            # Build kubectl get namespaces command
            cmd = ["kubectl", "get", "namespaces", "--context", cluster["context"]]

            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            # Add output format for parsing
            cmd.extend(["-o", "wide"])

            result = await self._run_command(cmd)
            if result["returncode"] != 0:
                return []

            # Parse namespaces output
            namespaces = []
            lines = result["stdout"].strip().split("\n")

            # Skip header line
            if lines and "NAME" in lines[0]:
                lines = lines[1:]

            for line in lines:
                if not line.strip():
                    continue

                parts = line.split()
                if len(parts) < 2:
                    continue

                namespace_name = parts[0]
                status = parts[1]

                # Apply filter
                if (
                    namespace_filter
                    and namespace_filter.lower() not in namespace_name.lower()
                ):
                    continue

                # Get additional namespace details
                namespace_details = await self._get_namespace_details(
                    cluster, namespace_name, kubeconfig
                )

                namespaces.append(
                    {
                        "name": namespace_name,
                        "status": status,
                        "labels": namespace_details.get("labels", {}),
                        "annotations": namespace_details.get("annotations", {}),
                    }
                )

            return namespaces

        except Exception:
            return []

    async def _get_namespace_details(
        self, cluster: Dict[str, Any], namespace: str, kubeconfig: str
    ) -> Dict[str, Any]:
        """Get detailed information about a namespace."""
        try:
            cmd = [
                "kubectl",
                "get",
                "namespace",
                namespace,
                "--context",
                cluster["context"],
                "-o",
                "jsonpath={.metadata.labels}{';'}{.metadata.annotations}",
            ]

            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(cmd)
            if result["returncode"] != 0:
                return {"labels": {}, "annotations": {}}

            # Parse the output (labels;annotations)
            parts = result["stdout"].split(";")
            labels = {}
            annotations = {}

            if len(parts) > 0 and parts[0].strip():
                # Parse labels (basic parsing)
                labels_str = parts[0].strip()
                if labels_str and labels_str != "map[]":
                    # This is a simplified parser - in production, you'd want more robust JSON parsing
                    pass

            if len(parts) > 1 and parts[1].strip():
                # Parse annotations (basic parsing)
                annotations_str = parts[1].strip()
                if annotations_str and annotations_str != "map[]":
                    # This is a simplified parser - in production, you'd want more robust JSON parsing
                    pass

            return {"labels": labels, "annotations": annotations}

        except Exception:
            return {"labels": {}, "annotations": {}}

    def _create_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Create a summary of GVRC discovery results."""
        summary = {
            "total_resources": 0,
            "total_namespaces": 0,
            "resource_categories": set(),
            "common_resources": set(),
            "cluster_specific_resources": {},
            "namespace_distribution": {},
        }

        all_resources = set()
        cluster_resources = {}

        for cluster_name, cluster_result in results.items():
            if cluster_result.get("status") != "success":
                continue

            # Count resources and namespaces
            resources = cluster_result.get("resources", [])
            namespaces = cluster_result.get("namespaces", [])

            summary["total_resources"] += len(resources)
            summary["total_namespaces"] += len(namespaces)

            # Track resources per cluster
            cluster_resource_names = set()
            for resource in resources:
                resource_name = resource["name"]
                cluster_resource_names.add(resource_name)
                all_resources.add(resource_name)

                # Collect categories
                for category in resource.get("categories", []):
                    summary["resource_categories"].add(category)

            cluster_resources[cluster_name] = cluster_resource_names

            # Track namespace distribution
            summary["namespace_distribution"][cluster_name] = len(namespaces)

        # Find common resources (present in all clusters)
        if cluster_resources:
            summary["common_resources"] = set.intersection(*cluster_resources.values())

        # Find cluster-specific resources
        for cluster_name, resources in cluster_resources.items():
            unique_resources = resources - summary["common_resources"]
            if unique_resources:
                summary["cluster_specific_resources"][cluster_name] = list(
                    unique_resources
                )

        # Convert sets to lists for JSON serialization
        summary["resource_categories"] = list(summary["resource_categories"])
        summary["common_resources"] = list(summary["common_resources"])

        return summary

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
                "resource_filter": {
                    "type": "string",
                    "description": "Filter resources by name pattern",
                },
                "namespace_filter": {
                    "type": "string",
                    "description": "Filter namespaces by name pattern",
                },
                "all_namespaces": {
                    "type": "boolean",
                    "description": "Discover resources across all namespaces",
                    "default": False,
                },
                "api_resources": {
                    "type": "boolean",
                    "description": "Include built-in API resources",
                    "default": True,
                },
                "custom_resources": {
                    "type": "boolean",
                    "description": "Include custom resources (CRDs)",
                    "default": True,
                },
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by resource categories (e.g., 'all', 'core', 'extensions')",
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
                    "enum": ["summary", "detailed", "json"],
                    "default": "summary",
                },
            },
            "required": [],
        }
