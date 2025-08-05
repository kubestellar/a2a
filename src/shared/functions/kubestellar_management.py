"""KubeStellar-specific multi-cluster management utilities with deep search and binding policy integration.

Based on KubeStellar 2024 architecture with WDS, ITS, WEC, and OCM integration.
Supports binding policies, workload transformations, and status management.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..base_functions import BaseFunction


@dataclass
class KubeStellarSpace:
    """KubeStellar space information (WDS/ITS)."""

    name: str
    type: str  # 'wds', 'its', 'wec'
    cluster: str
    context: str
    status: str
    api_resources: List[str]
    namespaces: List[str]
    binding_policies: int = 0
    work_statuses: int = 0
    manifest_works: int = 0


@dataclass
class BindingPolicy:
    """KubeStellar binding policy with 2024 architecture support."""

    name: str
    namespace: str
    wds_cluster: str
    object_selectors: List[Dict[str, Any]]
    cluster_selectors: List[Dict[str, Any]]
    workload_transformations: Optional[Dict[str, Any]] = None
    singleton_status_return: bool = False
    status: Dict[str, Any] = None
    created: str = ""
    binding_objects: List[str] = None


@dataclass
class WorkStatus:
    """KubeStellar work status with OCM integration."""

    name: str
    namespace: str
    its_cluster: str
    source_workload: Dict[str, str]
    managed_clusters: List[Dict[str, Any]]
    manifest_conditions: List[Dict[str, Any]]
    applied_objects: List[Dict[str, str]]
    sync_status: str
    created: str


@dataclass
class ManifestWork:
    """OCM ManifestWork object information."""

    name: str
    namespace: str  # mailbox namespace
    its_cluster: str
    target_cluster: str
    workloads: List[Dict[str, Any]]
    conditions: List[Dict[str, str]]
    applied_resources: List[Dict[str, str]]
    status: str


class KubeStellarManagementFunction(BaseFunction):
    """Enhanced KubeStellar multi-cluster management with deep search and binding policy integration."""

    def __init__(self):
        super().__init__(
            name="kubestellar_management",
            description="Advanced KubeStellar multi-cluster resource management with deep search capabilities, binding policy integration, work status tracking, and comprehensive cluster topology analysis. Provides detailed insights into resource distribution, policy compliance, and cross-cluster relationships.",
        )

    async def execute(
        self,
        operation: str = "deep_search",
        resource_types: List[str] = None,
        namespace_names: List[str] = None,
        all_namespaces: bool = True,
        cluster_names: List[str] = None,
        all_clusters: bool = True,
        label_selector: str = "",
        field_selector: str = "",
        binding_policies: bool = True,
        work_statuses: bool = True,
        placement_analysis: bool = True,
        deep_analysis: bool = True,
        include_wds: bool = False,
        kubeconfig: str = "",
        output_format: str = "comprehensive",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute KubeStellar management operations with deep search and policy integration.

        Args:
            operation: Operation type (deep_search, policy_analysis, resource_inventory, topology_map)
            resource_types: Specific resource types to search for
            namespace_names: Specific namespaces to analyze
            all_namespaces: Include all namespaces in search
            cluster_names: Specific clusters to analyze
            all_clusters: Include all clusters in analysis
            label_selector: Label selector for resource filtering
            field_selector: Field selector for resource filtering
            binding_policies: Include binding policy analysis
            work_statuses: Include work status tracking
            placement_analysis: Analyze resource placement strategies
            deep_analysis: Perform deep dependency and relationship analysis
            include_wds: Include WDS clusters in analysis
            kubeconfig: Path to kubeconfig file
            output_format: Output format (comprehensive, summary, detailed, json)

        Returns:
            Dictionary with comprehensive KubeStellar analysis results
        """
        try:
            # Discover KubeStellar cluster topology
            clusters = await self._discover_kubestellar_topology(
                kubeconfig, include_wds
            )
            if not clusters:
                return {
                    "status": "error",
                    "error": "No KubeStellar clusters discovered",
                }

            # Filter clusters if specified
            if cluster_names and not all_clusters:
                clusters = [c for c in clusters if c["name"] in cluster_names]

            # Execute operation based on type
            if operation == "deep_search":
                return await self._perform_deep_search(
                    clusters,
                    resource_types,
                    namespace_names,
                    all_namespaces,
                    label_selector,
                    field_selector,
                    binding_policies,
                    work_statuses,
                    placement_analysis,
                    deep_analysis,
                    kubeconfig,
                    output_format,
                )
            elif operation == "policy_analysis":
                return await self._analyze_binding_policies(
                    clusters, kubeconfig, output_format
                )
            elif operation == "resource_inventory":
                return await self._create_resource_inventory(
                    clusters,
                    resource_types,
                    namespace_names,
                    all_namespaces,
                    kubeconfig,
                    output_format,
                )
            elif operation == "topology_map":
                return await self._create_topology_map(
                    clusters, kubeconfig, output_format
                )
            else:
                return {
                    "status": "error",
                    "error": f"Unsupported operation: {operation}",
                }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to execute KubeStellar management operation: {str(e)}",
            }

    async def _discover_kubestellar_topology(
        self, kubeconfig: str, include_wds: bool
    ) -> List[Dict[str, Any]]:
        """Discover KubeStellar 2024 architecture topology with WDS, ITS, and WEC classification."""
        try:
            spaces = []

            # Get all kubeconfig contexts
            cmd = ["kubectl", "config", "get-contexts", "-o", "name"]
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(cmd)
            if result["returncode"] != 0:
                return []

            contexts = result["stdout"].strip().split("\n")

            # Analyze each context for KubeStellar 2024 components
            for context in contexts:
                if not context.strip():
                    continue

                # Classify space type based on 2024 architecture
                space_info = await self._classify_kubestellar_space(context, kubeconfig)

                # Skip WDS spaces unless explicitly requested
                if space_info["type"] == "wds" and not include_wds:
                    continue

                # Test connectivity
                test_cmd = ["kubectl", "cluster-info", "--context", context]
                if kubeconfig:
                    test_cmd.extend(["--kubeconfig", kubeconfig])

                test_result = await self._run_command(test_cmd)
                if test_result["returncode"] == 0:
                    space_info["status"] = "Ready"
                    space_info["context"] = context
                    spaces.append(space_info)

            return spaces

        except Exception:
            return []

    async def _classify_kubestellar_space(
        self, context: str, kubeconfig: str
    ) -> Dict[str, Any]:
        """Classify KubeStellar 2024 space type (WDS, ITS, WEC) and gather metadata."""
        try:
            space_info = {
                "name": context,
                "type": "unknown",
                "cluster": context,
                "api_resources": [],
                "namespaces": [],
                "kubestellar_components": {},
                "ocm_components": {},
            }

            # Get CRDs to identify space type
            cmd = [
                "kubectl",
                "api-resources",
                "--context",
                context,
                "--api-group=control.kubestellar.io",
            ]
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(cmd)
            kubestellar_resources = (
                result["stdout"] if result["returncode"] == 0 else ""
            )

            # Get OCM CRDs
            ocm_cmd = [
                "kubectl",
                "api-resources",
                "--context",
                context,
                "--api-group=cluster.open-cluster-management.io",
            ]
            if kubeconfig:
                ocm_cmd.extend(["--kubeconfig", kubeconfig])

            ocm_result = await self._run_command(ocm_cmd)
            ocm_resources = (
                ocm_result["stdout"] if ocm_result["returncode"] == 0 else ""
            )

            # Classify based on KubeStellar 2024 architecture
            if "bindingpolicies" in kubestellar_resources.lower():
                space_info["type"] = "wds"  # Workload Description Space
                space_info["kubestellar_components"]["binding_controller"] = True
                space_info["kubestellar_components"]["controller_manager"] = True
            elif "workstatuses" in kubestellar_resources.lower():
                space_info["type"] = "its"  # Inventory and Transport Space
                space_info["kubestellar_components"]["transport_controller"] = True
                space_info["kubestellar_components"]["status_controller"] = True
            elif "managedclusters" in ocm_resources.lower():
                space_info["type"] = "its"  # ITS with OCM Hub
                space_info["ocm_components"]["cluster_manager"] = True
            elif "manifestworks" in ocm_resources.lower():
                # Could be either ITS or WEC with OCM agent
                if context.lower().startswith("wds") or "-wds-" in context.lower():
                    space_info["type"] = "wds"
                else:
                    space_info["type"] = "wec"  # Workload Execution Cluster
                    space_info["ocm_components"]["klusterlet"] = True
            else:
                # Check naming patterns for space type
                context_lower = context.lower()
                if context_lower.startswith("wds") or "-wds-" in context_lower:
                    space_info["type"] = "wds"
                elif context_lower.startswith("its") or "-its-" in context_lower:
                    space_info["type"] = "its"
                elif context_lower.startswith("wec") or "-wec-" in context_lower:
                    space_info["type"] = "wec"
                else:
                    space_info["type"] = "standard"

            # Get KubeStellar-specific namespaces
            space_info["namespaces"] = await self._get_kubestellar_namespaces(
                context, kubeconfig
            )

            # Get API resources count
            space_info["api_resources"] = await self._get_kubestellar_api_resources(
                context, kubeconfig
            )

            return space_info

        except Exception:
            return {
                "name": context,
                "type": "unknown",
                "cluster": context,
                "api_resources": [],
                "namespaces": [],
                "kubestellar_components": {},
                "ocm_components": {},
            }

    async def _get_kubestellar_namespaces(
        self, context: str, kubeconfig: str
    ) -> List[str]:
        """Get KubeStellar-related namespaces."""
        try:
            cmd = ["kubectl", "get", "namespaces", "--context", context, "-o", "json"]
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(cmd)
            if result["returncode"] != 0:
                return []

            ns_data = json.loads(result["stdout"])
            kubestellar_namespaces = []

            for ns in ns_data.get("items", []):
                ns_name = ns["metadata"]["name"]
                labels = ns["metadata"].get("labels", {})

                # Identify KubeStellar-related namespaces
                if (
                    ns_name.startswith("kubestellar")
                    or ns_name.startswith("kube-")
                    or ns_name.startswith("open-cluster-management")
                    or "kubestellar.io" in str(labels)
                    or "open-cluster-management.io" in str(labels)
                    or ns_name in ["customization-properties"]
                ):  # KubeStellar 2024 namespace
                    kubestellar_namespaces.append(ns_name)

            return kubestellar_namespaces

        except Exception:
            return []

    async def _get_kubestellar_api_resources(
        self, context: str, kubeconfig: str
    ) -> List[str]:
        """Get KubeStellar-specific API resources."""
        try:
            resources = []

            # Get KubeStellar API resources
            for api_group in [
                "control.kubestellar.io",
                "cluster.open-cluster-management.io",
                "work.open-cluster-management.io",
            ]:
                cmd = [
                    "kubectl",
                    "api-resources",
                    "--context",
                    context,
                    f"--api-group={api_group}",
                ]
                if kubeconfig:
                    cmd.extend(["--kubeconfig", kubeconfig])

                result = await self._run_command(cmd)
                if result["returncode"] == 0:
                    lines = result["stdout"].strip().split("\n")
                    for line in lines[1:]:  # Skip header
                        if line.strip():
                            parts = line.split()
                            if len(parts) >= 1:
                                resources.append(parts[0])

            return resources

        except Exception:
            return []

    async def _get_kubestellar_info(
        self, context: str, kubeconfig: str
    ) -> Dict[str, Any]:
        """Get KubeStellar-specific information for a cluster."""
        try:
            info = {
                "version": None,
                "components": [],
                "api_resources": [],
                "namespaces": [],
            }

            # Get KubeStellar API resources
            cmd = ["kubectl", "api-resources", "--context", context]
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(cmd)
            if result["returncode"] == 0:
                lines = result["stdout"].strip().split("\n")
                for line in lines:
                    if "kubestellar.io" in line.lower():
                        parts = line.split()
                        if len(parts) >= 3:
                            info["api_resources"].append(
                                {
                                    "name": parts[0],
                                    "api_version": parts[2],
                                    "kind": parts[4] if len(parts) > 4 else "",
                                }
                            )

            # Get KubeStellar namespaces
            ns_cmd = [
                "kubectl",
                "get",
                "namespaces",
                "--context",
                context,
                "-o",
                "json",
            ]
            if kubeconfig:
                ns_cmd.extend(["--kubeconfig", kubeconfig])

            ns_result = await self._run_command(ns_cmd)
            if ns_result["returncode"] == 0:
                ns_data = json.loads(ns_result["stdout"])
                for ns in ns_data.get("items", []):
                    ns_name = ns["metadata"]["name"]
                    labels = ns["metadata"].get("labels", {})

                    # Check for KubeStellar-related namespaces
                    if (
                        ns_name.startswith("kubestellar")
                        or "kubestellar.io" in str(labels)
                        or ns_name in ["kube-system", "default"]
                    ):
                        info["namespaces"].append(
                            {
                                "name": ns_name,
                                "labels": labels,
                                "status": ns["status"]["phase"],
                            }
                        )

            return info

        except Exception:
            return {}

    async def _perform_deep_search(
        self,
        clusters: List[Dict[str, Any]],
        resource_types: Optional[List[str]],
        namespace_names: Optional[List[str]],
        all_namespaces: bool,
        label_selector: str,
        field_selector: str,
        binding_policies: bool,
        work_statuses: bool,
        placement_analysis: bool,
        deep_analysis: bool,
        kubeconfig: str,
        output_format: str,
    ) -> Dict[str, Any]:
        """Perform deep search across KubeStellar clusters."""
        try:
            results = {
                "status": "success",
                "operation": "deep_search",
                "clusters_analyzed": len(clusters),
                "resource_summary": {},
                "binding_policies": {},
                "work_statuses": {},
                "placement_analysis": {},
                "dependency_map": {},
                "cluster_results": {},
            }

            # Default resource types for KubeStellar
            if not resource_types:
                resource_types = [
                    "pods",
                    "services",
                    "deployments",
                    "replicasets",
                    "configmaps",
                    "secrets",
                    "persistentvolumeclaims",
                    "workstatuses",
                    "bindings",
                    "placements",
                    "placementdecisions",
                ]

            # Execute deep search on each cluster
            for cluster in clusters:
                cluster_result = await self._deep_search_cluster(
                    cluster,
                    resource_types,
                    namespace_names,
                    all_namespaces,
                    label_selector,
                    field_selector,
                    binding_policies,
                    work_statuses,
                    kubeconfig,
                )
                results["cluster_results"][cluster["name"]] = cluster_result

            # Aggregate results
            results["resource_summary"] = self._aggregate_resource_summary(
                results["cluster_results"]
            )

            if binding_policies:
                results["binding_policies"] = await self._aggregate_binding_policies(
                    clusters, kubeconfig
                )

            if work_statuses:
                results["work_statuses"] = await self._aggregate_work_statuses(
                    clusters, kubeconfig
                )

            if placement_analysis:
                results["placement_analysis"] = self._analyze_resource_placement(
                    results["cluster_results"]
                )

            if deep_analysis:
                results["dependency_map"] = self._create_dependency_map(
                    results["cluster_results"]
                )

            return results

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to perform deep search: {str(e)}",
            }

    async def _deep_search_cluster(
        self,
        cluster: Dict[str, Any],
        resource_types: List[str],
        namespace_names: Optional[List[str]],
        all_namespaces: bool,
        label_selector: str,
        field_selector: str,
        binding_policies: bool,
        work_statuses: bool,
        kubeconfig: str,
    ) -> Dict[str, Any]:
        """Perform deep search on a single cluster."""
        try:
            cluster_result = {
                "cluster": cluster["name"],
                "cluster_type": cluster.get("type", "unknown"),
                "status": "success",
                "namespaces": {},
                "resources_by_type": {},
                "total_resources": 0,
                "kubestellar_resources": [],
            }

            # Get target namespaces
            target_namespaces = await self._get_target_namespaces(
                cluster, namespace_names, all_namespaces, kubeconfig
            )

            # Search each namespace for resources
            for namespace in target_namespaces:
                namespace_resources = await self._search_namespace_resources(
                    cluster,
                    namespace,
                    resource_types,
                    label_selector,
                    field_selector,
                    kubeconfig,
                )

                cluster_result["namespaces"][namespace] = namespace_resources
                cluster_result["total_resources"] += len(namespace_resources)

                # Categorize resources by type
                for resource in namespace_resources:
                    resource_type = resource["kind"].lower()
                    if resource_type not in cluster_result["resources_by_type"]:
                        cluster_result["resources_by_type"][resource_type] = []
                    cluster_result["resources_by_type"][resource_type].append(resource)

                    # Track KubeStellar-specific resources
                    if self._is_kubestellar_resource(resource):
                        cluster_result["kubestellar_resources"].append(resource)

            return cluster_result

        except Exception as e:
            return {"cluster": cluster["name"], "status": "error", "error": str(e)}

    async def _get_target_namespaces(
        self,
        cluster: Dict[str, Any],
        namespace_names: Optional[List[str]],
        all_namespaces: bool,
        kubeconfig: str,
    ) -> List[str]:
        """Get list of target namespaces for search."""
        try:
            if namespace_names:
                return namespace_names

            if not all_namespaces:
                return ["default"]

            # Get all namespaces
            cmd = [
                "kubectl",
                "get",
                "namespaces",
                "--context",
                cluster["context"],
                "-o",
                "name",
            ]
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(cmd)
            if result["returncode"] != 0:
                return ["default"]

            namespaces = []
            for line in result["stdout"].strip().split("\n"):
                if line.startswith("namespace/"):
                    ns_name = line.replace("namespace/", "")
                    namespaces.append(ns_name)

            return namespaces

        except Exception:
            return ["default"]

    async def _search_namespace_resources(
        self,
        cluster: Dict[str, Any],
        namespace: str,
        resource_types: List[str],
        label_selector: str,
        field_selector: str,
        kubeconfig: str,
    ) -> List[Dict[str, Any]]:
        """Search for resources in a specific namespace."""
        try:
            resources = []

            for resource_type in resource_types:
                cmd = [
                    "kubectl",
                    "get",
                    resource_type,
                    "--namespace",
                    namespace,
                    "--context",
                    cluster["context"],
                    "-o",
                    "json",
                ]

                if kubeconfig:
                    cmd.extend(["--kubeconfig", kubeconfig])

                if label_selector:
                    cmd.extend(["-l", label_selector])

                if field_selector:
                    cmd.extend(["--field-selector", field_selector])

                result = await self._run_command(cmd)
                if result["returncode"] == 0:
                    try:
                        resource_data = json.loads(result["stdout"])
                        for item in resource_data.get("items", []):
                            resource_info = {
                                "name": item["metadata"]["name"],
                                "kind": item["kind"],
                                "api_version": item["apiVersion"],
                                "namespace": namespace,
                                "cluster": cluster["name"],
                                "labels": item["metadata"].get("labels", {}),
                                "annotations": item["metadata"].get("annotations", {}),
                                "created": item["metadata"]["creationTimestamp"],
                                "uid": item["metadata"]["uid"],
                                "resource_version": item["metadata"]["resourceVersion"],
                            }

                            # Add resource-specific information
                            if resource_type == "pods":
                                resource_info["phase"] = item.get("status", {}).get(
                                    "phase"
                                )
                                resource_info["node"] = item.get("spec", {}).get(
                                    "nodeName"
                                )
                            elif resource_type == "workstatuses":
                                resource_info["work_status_details"] = item.get(
                                    "status", {}
                                )

                            resources.append(resource_info)

                    except json.JSONDecodeError:
                        continue

            return resources

        except Exception:
            return []

    def _is_kubestellar_resource(self, resource: Dict[str, Any]) -> bool:
        """Check if a resource is KubeStellar-specific."""
        api_version = resource.get("api_version", "")
        kind = resource.get("kind", "")
        labels = resource.get("labels", {})
        annotations = resource.get("annotations", {})

        # Check API version
        if "kubestellar.io" in api_version:
            return True

        # Check labels and annotations
        for key in list(labels.keys()) + list(annotations.keys()):
            if "kubestellar" in key.lower():
                return True

        # Check specific KubeStellar resource types
        kubestellar_kinds = [
            "WorkStatus",
            "BindingPolicy",
            "Placement",
            "PlacementDecision",
        ]

        return kind in kubestellar_kinds

    def _aggregate_resource_summary(
        self, cluster_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Aggregate resource summary across all clusters."""
        summary = {
            "total_clusters": len(cluster_results),
            "total_resources": 0,
            "resources_by_type": {},
            "resources_by_cluster": {},
            "kubestellar_resources": 0,
            "cluster_types": {},
        }

        for cluster_name, cluster_result in cluster_results.items():
            if cluster_result.get("status") != "success":
                continue

            cluster_total = cluster_result.get("total_resources", 0)
            summary["total_resources"] += cluster_total
            summary["resources_by_cluster"][cluster_name] = cluster_total

            # Aggregate by cluster type
            cluster_type = cluster_result.get("cluster_type", "unknown")
            if cluster_type not in summary["cluster_types"]:
                summary["cluster_types"][cluster_type] = {"count": 0, "resources": 0}
            summary["cluster_types"][cluster_type]["count"] += 1
            summary["cluster_types"][cluster_type]["resources"] += cluster_total

            # Aggregate by resource type
            for resource_type, resources in cluster_result.get(
                "resources_by_type", {}
            ).items():
                if resource_type not in summary["resources_by_type"]:
                    summary["resources_by_type"][resource_type] = 0
                summary["resources_by_type"][resource_type] += len(resources)

            # Count KubeStellar resources
            summary["kubestellar_resources"] += len(
                cluster_result.get("kubestellar_resources", [])
            )

        return summary

    async def _aggregate_binding_policies(
        self, clusters: List[Dict[str, Any]], kubeconfig: str
    ) -> Dict[str, Any]:
        """Aggregate binding policy information across clusters."""
        try:
            policies = {
                "total_policies": 0,
                "policies_by_cluster": {},
                "policy_details": [],
            }

            for cluster in clusters:
                cluster_policies = await self._get_binding_policies(cluster, kubeconfig)
                policies["policies_by_cluster"][cluster["name"]] = len(cluster_policies)
                policies["total_policies"] += len(cluster_policies)
                policies["policy_details"].extend(cluster_policies)

            return policies

        except Exception:
            return {"error": "Failed to aggregate binding policies"}

    async def _get_binding_policies(
        self, cluster: Dict[str, Any], kubeconfig: str
    ) -> List[Dict[str, Any]]:
        """Get binding policies from a cluster."""
        try:
            policies = []

            # Try to get binding policies (KubeStellar specific)
            cmd = [
                "kubectl",
                "get",
                "bindingpolicies",
                "--context",
                cluster["context"],
                "-o",
                "json",
            ]
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(cmd)
            if result["returncode"] == 0:
                policy_data = json.loads(result["stdout"])
                for item in policy_data.get("items", []):
                    policies.append(
                        {
                            "name": item["metadata"]["name"],
                            "namespace": item["metadata"].get("namespace", ""),
                            "cluster": cluster["name"],
                            "spec": item.get("spec", {}),
                            "status": item.get("status", {}),
                            "created": item["metadata"]["creationTimestamp"],
                        }
                    )

            return policies

        except Exception:
            return []

    async def _aggregate_work_statuses(
        self, clusters: List[Dict[str, Any]], kubeconfig: str
    ) -> Dict[str, Any]:
        """Aggregate work status information across clusters."""
        try:
            statuses = {
                "total_work_statuses": 0,
                "statuses_by_cluster": {},
                "status_details": [],
            }

            for cluster in clusters:
                cluster_statuses = await self._get_work_statuses(cluster, kubeconfig)
                statuses["statuses_by_cluster"][cluster["name"]] = len(cluster_statuses)
                statuses["total_work_statuses"] += len(cluster_statuses)
                statuses["status_details"].extend(cluster_statuses)

            return statuses

        except Exception:
            return {"error": "Failed to aggregate work statuses"}

    async def _get_work_statuses(
        self, cluster: Dict[str, Any], kubeconfig: str
    ) -> List[Dict[str, Any]]:
        """Get work statuses from a cluster."""
        try:
            statuses = []

            cmd = [
                "kubectl",
                "get",
                "workstatuses",
                "--context",
                cluster["context"],
                "-o",
                "json",
            ]
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(cmd)
            if result["returncode"] == 0:
                status_data = json.loads(result["stdout"])
                for item in status_data.get("items", []):
                    statuses.append(
                        {
                            "name": item["metadata"]["name"],
                            "namespace": item["metadata"].get("namespace", ""),
                            "cluster": cluster["name"],
                            "spec": item.get("spec", {}),
                            "status": item.get("status", {}),
                            "created": item["metadata"]["creationTimestamp"],
                        }
                    )

            return statuses

        except Exception:
            return []

    def _analyze_resource_placement(
        self, cluster_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze resource placement patterns across clusters."""
        placement_analysis = {
            "distribution_patterns": {},
            "cross_cluster_resources": {},
            "placement_efficiency": {},
            "recommendations": [],
        }

        # Analyze resource distribution patterns
        resource_distribution = {}
        for cluster_name, cluster_result in cluster_results.items():
            if cluster_result.get("status") != "success":
                continue

            for resource_type, resources in cluster_result.get(
                "resources_by_type", {}
            ).items():
                if resource_type not in resource_distribution:
                    resource_distribution[resource_type] = {}
                resource_distribution[resource_type][cluster_name] = len(resources)

        placement_analysis["distribution_patterns"] = resource_distribution

        # Generate placement recommendations
        recommendations = []
        for resource_type, distribution in resource_distribution.items():
            total_resources = sum(distribution.values())
            cluster_count = len(distribution)

            if cluster_count > 1:
                avg_per_cluster = total_resources / cluster_count
                for cluster, count in distribution.items():
                    if count > avg_per_cluster * 1.5:
                        recommendations.append(
                            f"Consider redistributing {resource_type} from {cluster} "
                            f"(has {count}, average is {avg_per_cluster:.1f})"
                        )

        placement_analysis["recommendations"] = recommendations

        return placement_analysis

    def _create_dependency_map(self, cluster_results: Dict[str, Any]) -> Dict[str, Any]:
        """Create a dependency map of resources across clusters."""
        dependency_map = {
            "cross_cluster_references": {},
            "resource_relationships": {},
            "orphaned_resources": [],
        }

        # Analyze cross-cluster references
        all_resources = {}
        for cluster_name, cluster_result in cluster_results.items():
            if cluster_result.get("status") != "success":
                continue

            for namespace, resources in cluster_result.get("namespaces", {}).items():
                for resource in resources:
                    resource_key = f"{cluster_name}/{namespace}/{resource['kind']}/{resource['name']}"
                    all_resources[resource_key] = resource

        # Find potential dependencies based on annotations and labels
        for resource_key, resource in all_resources.items():
            annotations = resource.get("annotations", {})
            labels = resource.get("labels", {})

            # Look for KubeStellar-specific dependency markers
            for key, value in {**annotations, **labels}.items():
                if "kubestellar" in key.lower() or "binding" in key.lower():
                    if resource_key not in dependency_map["resource_relationships"]:
                        dependency_map["resource_relationships"][resource_key] = []
                    dependency_map["resource_relationships"][resource_key].append(
                        {"type": "kubestellar_managed", "reference": f"{key}={value}"}
                    )

        return dependency_map

    async def _analyze_binding_policies(
        self, clusters: List[Dict[str, Any]], kubeconfig: str, output_format: str
    ) -> Dict[str, Any]:
        """Analyze binding policies across clusters."""
        try:
            # Implementation for binding policy analysis
            binding_analysis = await self._aggregate_binding_policies(
                clusters, kubeconfig
            )

            return {
                "status": "success",
                "operation": "policy_analysis",
                "binding_policies": binding_analysis,
                "clusters_analyzed": len(clusters),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to analyze binding policies: {str(e)}",
            }

    async def _create_resource_inventory(
        self,
        clusters: List[Dict[str, Any]],
        resource_types: Optional[List[str]],
        namespace_names: Optional[List[str]],
        all_namespaces: bool,
        kubeconfig: str,
        output_format: str,
    ) -> Dict[str, Any]:
        """Create comprehensive resource inventory."""
        try:
            # Implementation for resource inventory
            inventory = {
                "status": "success",
                "operation": "resource_inventory",
                "clusters": len(clusters),
                "inventory": {},
            }

            for cluster in clusters:
                cluster_inventory = await self._deep_search_cluster(
                    cluster,
                    resource_types or ["pods", "services", "deployments"],
                    namespace_names,
                    all_namespaces,
                    "",
                    "",
                    False,
                    False,
                    kubeconfig,
                )
                inventory["inventory"][cluster["name"]] = cluster_inventory

            return inventory

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to create resource inventory: {str(e)}",
            }

    async def _create_topology_map(
        self, clusters: List[Dict[str, Any]], kubeconfig: str, output_format: str
    ) -> Dict[str, Any]:
        """Create KubeStellar topology map."""
        try:
            topology = {
                "status": "success",
                "operation": "topology_map",
                "control_planes": [],
                "wec_clusters": [],
                "wds_clusters": [],
                "standard_clusters": [],
                "cluster_relationships": {},
            }

            for cluster in clusters:
                cluster_type = cluster.get("type", "unknown")
                cluster_info = {
                    "name": cluster["name"],
                    "context": cluster["context"],
                    "kubestellar_info": cluster.get("kubestellar_info", {}),
                }

                if cluster_type == "control_plane":
                    topology["control_planes"].append(cluster_info)
                elif cluster_type == "wec":
                    topology["wec_clusters"].append(cluster_info)
                elif cluster_type == "wds":
                    topology["wds_clusters"].append(cluster_info)
                else:
                    topology["standard_clusters"].append(cluster_info)

            return topology

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to create topology map: {str(e)}",
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
                "operation": {
                    "type": "string",
                    "description": "Operation type to perform",
                    "enum": [
                        "deep_search",
                        "policy_analysis",
                        "resource_inventory",
                        "topology_map",
                    ],
                    "default": "deep_search",
                },
                "resource_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific resource types to search for (pods, services, deployments, workstatuses, etc.)",
                },
                "namespace_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific namespace names to analyze",
                },
                "all_namespaces": {
                    "type": "boolean",
                    "description": "Include all namespaces in search",
                    "default": True,
                },
                "cluster_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific cluster names to analyze",
                },
                "all_clusters": {
                    "type": "boolean",
                    "description": "Include all clusters in analysis",
                    "default": True,
                },
                "label_selector": {
                    "type": "string",
                    "description": "Label selector for resource filtering (e.g., 'app=nginx')",
                },
                "field_selector": {
                    "type": "string",
                    "description": "Field selector for resource filtering (e.g., 'status.phase=Running')",
                },
                "binding_policies": {
                    "type": "boolean",
                    "description": "Include binding policy analysis",
                    "default": True,
                },
                "work_statuses": {
                    "type": "boolean",
                    "description": "Include work status tracking",
                    "default": True,
                },
                "placement_analysis": {
                    "type": "boolean",
                    "description": "Analyze resource placement strategies",
                    "default": True,
                },
                "deep_analysis": {
                    "type": "boolean",
                    "description": "Perform deep dependency and relationship analysis",
                    "default": True,
                },
                "include_wds": {
                    "type": "boolean",
                    "description": "Include WDS clusters in analysis",
                    "default": False,
                },
                "kubeconfig": {
                    "type": "string",
                    "description": "Path to kubeconfig file",
                },
                "output_format": {
                    "type": "string",
                    "description": "Output format for results",
                    "enum": ["comprehensive", "summary", "detailed", "json"],
                    "default": "comprehensive",
                },
            },
            "required": [],
        }
