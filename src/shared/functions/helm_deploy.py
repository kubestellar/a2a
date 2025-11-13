"""Helm chart deployment function with KubeStellar binding policy integration.

Provides multi-cluster Helm deployments with automatic KubeStellar integration:
- Multi-cluster deployment with cluster-specific configurations
- Automatic resource labeling and BindingPolicy creation
- Namespace management with KubeStellar metadata
- All standard Helm operations (install, upgrade, uninstall, status, history)

Key KubeStellar concepts:
- ITS: Inventory & Template Space (where workload templates are stored)
- WDS: Workload Description Space (where binding policies are created)
- WEC: Workload Execution Clusters (where apps actually run)
- BindingPolicy: Defines workload distribution rules based on cluster labels

KubeStellar Deployment Flow:
1. Deploy to ITS cluster first (e.g., its1) - this creates the template
2. Create BindingPolicy in WDS cluster (e.g., wds1) with cluster selectors
3. KubeStellar automatically propagates workloads to WECs matching the selectors

Example for KubeStellar deployment:
    helm_deploy(
        chart_name="nginx",
        repository_url="https://charts.bitnami.com/bitnami",
        target_clusters=["its1"],  # Deploy to ITS only
        namespace="production",
        wait=false,  # Avoid timeouts
        create_binding_policy=true,
        wds_context="wds1",  # WDS cluster for policy
        cluster_selector_labels={"location-group": "edge"}  # Selects WECs
    )

To check cluster labels:
    kubectl get managedclusters -A --show-labels
"""

import asyncio
import json
import tempfile
from typing import Any, Dict, List, Optional

import yaml

from src.shared.base_functions import BaseFunction


class HelmDeployFunction(BaseFunction):
    """Multi-cluster Helm deployment with KubeStellar integration.

    Features:
    - Parallel deployment across multiple clusters
    - Automatic KubeStellar resource labeling and BindingPolicy creation
    - Cluster-specific configurations (different values per cluster)
    - Namespace management with KubeStellar metadata
    - All Helm operations: install, upgrade, uninstall, status, history
    """

    def __init__(self) -> None:
        super().__init__(
            name="helm_deploy",
            description="Deploy Helm charts with KubeStellar multi-cluster support. For KubeStellar: deploy to ITS cluster (e.g., its1) and create BindingPolicy in WDS (e.g., wds1) to propagate to WECs. Use cluster_selector_labels to match ManagedCluster labels. Supports install/upgrade/uninstall/status/history operations. Always use wait=false to avoid timeouts.",
        )

    async def execute(
        self,
        chart_name: str = "",
        chart_version: str = "",
        repository_url: str = "",
        repository_name: str = "",
        chart_path: str = "",
        release_name: str = "",
        target_clusters: Optional[List[str]] = None,
        cluster_labels: Optional[List[str]] = None,
        namespace: str = "default",
        all_namespaces: bool = False,
        namespace_selector: str = "",
        target_namespaces: Optional[List[str]] = None,
        values_file: str = "",
        values_files: Optional[List[str]] = None,
        cluster_values: Optional[List[str]] = None,
        set_values: Optional[List[str]] = None,
        cluster_set_values: Optional[List[str]] = None,
        create_namespace: bool = True,
        wait: bool = True,
        timeout: str = "5m",
        atomic: bool = False,
        dry_run: bool = False,
        operation: str = "install",
        kubeconfig: str = "",
        remote_context: str = "",
        # KubeStellar specific parameters
        create_binding_policy: bool = True,
        binding_policy_name: str = "",
        cluster_selector_labels: Optional[Dict[str, str]] = None,
        kubestellar_labels: Optional[Dict[str, str]] = None,
        wds_context: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Deploy Helm charts across multiple clusters with KubeStellar integration.

        Process: discover clusters → prepare labels → execute Helm operation → create BindingPolicy
        Supports cluster-specific configurations and automatic KubeStellar resource management.

        Args:
            chart_name: Name of the Helm chart
            chart_version: Version of the chart to deploy
            repository_url: Helm repository URL
            repository_name: Helm repository name (if already added)
            chart_path: Local path to chart directory or .tgz file
            release_name: Name of the Helm release
            target_clusters: Names of clusters to deploy to (for KubeStellar, use ITS cluster like ["its1"])
            cluster_labels: Label selectors for cluster targeting (alternative to target_clusters)
            namespace: Target namespace for deployment
            all_namespaces: Deploy across all namespaces
            namespace_selector: Namespace label selector
            target_namespaces: Specific list of target namespaces
            values_file: Path to values file
            values_files: List of values files
            cluster_values: Per-cluster values files (cluster=values.yaml format)
            set_values: Set values (key=value format)
            cluster_set_values: Per-cluster set values (cluster=key=value format)
            create_namespace: Create namespace if it doesn't exist
            wait: Wait for deployment (use false to avoid timeouts)
            timeout: Deployment timeout (default: 5m)
            atomic: Atomic deployment (rollback on failure)
            dry_run: Perform dry run without actual deployment
            operation: Helm operation (install, upgrade, uninstall, status, history)
            kubeconfig: Path to kubeconfig file
            remote_context: Remote context for cluster discovery
            create_binding_policy: Create KubeStellar binding policy (default: true)
            binding_policy_name: Name for the binding policy (auto-generated if empty)
            cluster_selector_labels: Labels to select WECs (e.g., {"location-group": "edge"})
            kubestellar_labels: Additional labels for resources
            wds_context: WDS cluster context for policy creation (e.g., "wds1")

        Returns:
            Dictionary with deployment results and binding policy information
        """
        try:
            # Validate required parameters based on operation type
            validation_result = self._validate_inputs(
                chart_name,
                chart_path,
                repository_url,
                repository_name,
                operation,
                release_name,
            )
            if validation_result:
                return validation_result

            # Set defaults for optional parameters
            if not release_name:
                release_name = (
                    chart_name.replace("/", "-") if chart_name else "helm-release"
                )

            # Set default binding policy name
            if not binding_policy_name:
                binding_policy_name = f"{release_name}-helm-policy"

            # Discover available clusters (excludes WDS management clusters)
            all_clusters = await self._discover_clusters(kubeconfig, remote_context)
            if not all_clusters:
                return {"status": "error", "error": "No clusters discovered"}

            # Filter clusters by names or labels
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

            # Validate KubeStellar deployment pattern
            if create_binding_policy and wds_context:
                # Check if deploying to ITS cluster
                its_clusters = [
                    c for c in selected_clusters if self._is_its_cluster(c["name"])
                ]
                wec_clusters = [
                    c for c in selected_clusters if self._is_wec_cluster(c["name"])
                ]

                if wec_clusters and not its_clusters:
                    return {
                        "status": "error",
                        "error": "KubeStellar deployments should target ITS cluster (e.g., its1) not WEC clusters directly",
                        "suggestion": "Use target_clusters=['its1'] and cluster_selector_labels to select WECs",
                        "its_clusters": [
                            c["name"]
                            for c in all_clusters
                            if self._is_its_cluster(c["name"])
                        ],
                        "wec_clusters": [c["name"] for c in wec_clusters],
                    }

                if len(selected_clusters) > 1 and operation in ["install", "upgrade"]:
                    # Warn if deploying to multiple clusters with KubeStellar
                    self._log_warning(
                        f"Deploying to {len(selected_clusters)} clusters with KubeStellar. "
                        "Recommended: deploy to ITS only and use BindingPolicy for propagation"
                    )

            # Resolve target namespaces (explicit list, all namespaces, or default)
            target_ns_list = await self._resolve_target_namespaces(
                selected_clusters[0],
                all_namespaces,
                namespace_selector,
                target_namespaces,
                namespace,
                kubeconfig,
            )

            # Prepare KubeStellar-compatible labels for resources and BindingPolicy
            helm_labels = self._prepare_kubestellar_labels(
                release_name, chart_name, kubestellar_labels
            )

            # Create deployment plan summary
            deployment_plan = {
                "operation": operation,
                "release_name": release_name,
                "chart_name": chart_name,
                "chart_version": chart_version,
                "target_clusters": [c["name"] for c in selected_clusters],
                "target_namespaces": target_ns_list,
                "binding_policy": {
                    "create": create_binding_policy,
                    "name": binding_policy_name,
                    "cluster_selector_labels": cluster_selector_labels,
                },
                "kubestellar_labels": helm_labels,
            }

            # Return preview for dry-run mode
            if dry_run:
                return {
                    "status": "success",
                    "message": "DRY RUN - No actual deployment will occur",
                    "deployment_plan": deployment_plan,
                    "clusters_selected": len(selected_clusters),
                }

            # Execute Helm operation (install/upgrade/uninstall/status/history)
            if operation in ["install", "upgrade"]:
                result = await self._deploy_helm_chart(
                    selected_clusters,
                    chart_name,
                    chart_version,
                    repository_url,
                    repository_name,
                    chart_path,
                    release_name,
                    target_ns_list,
                    values_file,
                    values_files,
                    cluster_values,
                    set_values,
                    cluster_set_values,
                    create_namespace,
                    wait,
                    timeout,
                    atomic,
                    operation,
                    kubeconfig,
                    helm_labels,
                )
            elif operation == "uninstall":
                result = await self._uninstall_helm_chart(
                    selected_clusters, release_name, target_ns_list, kubeconfig
                )
            elif operation in ["status", "history"]:
                result = await self._get_helm_info(
                    selected_clusters,
                    release_name,
                    target_ns_list,
                    operation,
                    kubeconfig,
                )
            else:
                return {
                    "status": "error",
                    "error": f"Unsupported operation: {operation}",
                }

            # Create or update binding policy if requested
            binding_policy_result = None
            if (
                create_binding_policy
                and operation in ["install", "upgrade"]
                and result["status"] == "success"
            ):
                binding_policy_result = await self._create_binding_policy(
                    binding_policy_name,
                    release_name,
                    helm_labels,
                    cluster_selector_labels,
                    target_ns_list,
                    wds_context,
                    kubeconfig,
                )

            # Combine results
            final_result = {
                **result,
                "deployment_plan": deployment_plan,
                "binding_policy": binding_policy_result,
            }

            return final_result

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to execute Helm deployment: {str(e)}",
            }

    def _validate_inputs(
        self,
        chart_name: str,
        chart_path: str,
        repository_url: str,
        repository_name: str,
        operation: str,
        release_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Validate input parameters."""
        if operation in ["install", "upgrade"]:
            if not chart_name and not chart_path:
                return {
                    "status": "error",
                    "error": "Either chart_name or chart_path must be specified for install/upgrade operations",
                }

            if (
                chart_name
                and not repository_url
                and not repository_name
                and not chart_path
            ):
                return {
                    "status": "error",
                    "error": "repository_url, repository_name, or chart_path must be specified when using chart_name",
                }

        if operation in ["uninstall", "status", "history"]:
            if not release_name and not chart_name:
                return {
                    "status": "error",
                    "error": f"release_name is required for {operation} operation",
                }

        return None

    def _prepare_kubestellar_labels(
        self,
        release_name: str,
        chart_name: str,
        additional_labels: Optional[Dict[str, str]],
    ) -> Dict[str, str]:
        """Create standard K8s + KubeStellar labels for resources and BindingPolicy selection."""
        labels = {
            "app.kubernetes.io/managed-by": "Helm",
            "app.kubernetes.io/instance": release_name,
            "kubestellar.io/helm-chart": (
                chart_name.replace("/", "-") if chart_name else release_name
            ),
            "kubestellar.io/helm-release": release_name,
        }

        if chart_name:
            labels["app.kubernetes.io/name"] = chart_name.split("/")[-1]

        if additional_labels:
            labels.update(additional_labels)

        return labels

    async def _deploy_helm_chart(
        self,
        clusters: List[Dict[str, Any]],
        chart_name: str,
        chart_version: str,
        repository_url: str,
        repository_name: str,
        chart_path: str,
        release_name: str,
        target_namespaces: List[str],
        values_file: str,
        values_files: Optional[List[str]],
        cluster_values: Optional[List[str]],
        set_values: Optional[List[str]],
        cluster_set_values: Optional[List[str]],
        create_namespace: bool,
        wait: bool,
        timeout: str,
        atomic: bool,
        operation: str,
        kubeconfig: str,
        helm_labels: Dict[str, str],
    ) -> Dict[str, Any]:
        """Execute Helm install/upgrade across multiple clusters with cluster-specific configs."""
        results = {}

        # Parse per-cluster values and settings
        cluster_values_map = self._parse_cluster_values(cluster_values)
        cluster_set_values_map = self._parse_cluster_set_values(cluster_set_values)

        # Execute deployment on each cluster in parallel
        for cluster in clusters:
            cluster_result = await self._deploy_to_cluster(
                cluster,
                chart_name,
                chart_version,
                repository_url,
                repository_name,
                chart_path,
                release_name,
                target_namespaces,
                values_file,
                values_files,
                cluster_values_map,
                set_values,
                cluster_set_values_map,
                create_namespace,
                wait,
                timeout,
                atomic,
                operation,
                kubeconfig,
                helm_labels,
            )
            results[cluster["name"]] = cluster_result

        success_count = sum(1 for r in results.values() if r["status"] == "success")

        return {
            "status": "success" if success_count > 0 else "error",
            "operation": operation,
            "clusters_total": len(clusters),
            "clusters_succeeded": success_count,
            "clusters_failed": len(clusters) - success_count,
            "results": results,
        }

    def _parse_cluster_values(
        self, cluster_values: Optional[List[str]]
    ) -> Dict[str, str]:
        """Parse cluster-specific values files."""
        cluster_values_map = {}
        if cluster_values:
            for cluster_value in cluster_values:
                if "=" in cluster_value:
                    cluster_name, values_file = cluster_value.split("=", 1)
                    cluster_values_map[cluster_name.strip()] = values_file.strip()
        return cluster_values_map

    def _parse_cluster_set_values(
        self, cluster_set_values: Optional[List[str]]
    ) -> Dict[str, List[str]]:
        """Parse cluster-specific set values."""
        cluster_set_values_map: Dict[str, List[str]] = {}
        if cluster_set_values:
            for cluster_set_value in cluster_set_values:
                parts = cluster_set_value.split("=", 2)
                if len(parts) >= 3:
                    cluster_name = parts[0].strip()
                    key_value = f"{parts[1]}={parts[2]}"
                    if cluster_name not in cluster_set_values_map:
                        cluster_set_values_map[cluster_name] = []
                    cluster_set_values_map[cluster_name].append(key_value)
        return cluster_set_values_map

    async def _deploy_to_cluster(
        self,
        cluster: Dict[str, Any],
        chart_name: str,
        chart_version: str,
        repository_url: str,
        repository_name: str,
        chart_path: str,
        release_name: str,
        target_namespaces: List[str],
        values_file: str,
        values_files: Optional[List[str]],
        cluster_values_map: Dict[str, str],
        set_values: Optional[List[str]],
        cluster_set_values_map: Dict[str, List[str]],
        create_namespace: bool,
        wait: bool,
        timeout: str,
        atomic: bool,
        operation: str,
        kubeconfig: str,
        helm_labels: Dict[str, str],
    ) -> Dict[str, Any]:
        """Deploy Helm chart to a specific cluster."""
        try:
            namespace_results = {}

            for namespace in target_namespaces:
                # Create namespace if needed
                if create_namespace:
                    await self._ensure_namespace_exists(
                        cluster, namespace, kubeconfig, helm_labels
                    )

                # Build Helm command
                cmd = await self._build_helm_command(
                    operation,
                    release_name,
                    chart_name,
                    chart_version,
                    repository_url,
                    repository_name,
                    chart_path,
                    cluster,
                    namespace,
                    values_file,
                    values_files,
                    cluster_values_map,
                    set_values,
                    cluster_set_values_map,
                    wait,
                    timeout,
                    atomic,
                    kubeconfig,
                    helm_labels,
                )

                # Execute Helm command
                result = await self._run_command(cmd)

                if result["returncode"] == 0:
                    # Parse Helm output for release information
                    release_info = await self._parse_helm_output(
                        result["stdout"],
                        operation,
                        release_name,
                        cluster,
                        namespace,
                        kubeconfig,
                    )

                    # Label Helm secret for KubeStellar compatibility
                    await self._label_helm_secret(
                        cluster, namespace, release_name, helm_labels, kubeconfig
                    )

                    # Set status based on helm status output
                    helm_status = release_info.get("status", "unknown").lower()
                    if helm_status in ["deployed", "superseded"]:
                        result_status = "success"
                    else:
                        result_status = "error"

                    # Create result dict without overwriting status
                    result_info = {
                        k: v for k, v in release_info.items() if k != "status"
                    }
                    result_info["helm_status"] = release_info.get("status", "unknown")

                    namespace_results[namespace] = {
                        "status": result_status,
                        "output": result["stdout"],
                        **result_info,
                    }
                else:
                    error_output = result["stderr"] or result["stdout"]
                    namespace_results[namespace] = {
                        "status": "error",
                        "error": f"Helm {operation} failed: {error_output}",
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

    async def _build_helm_command(
        self,
        operation: str,
        release_name: str,
        chart_name: str,
        chart_version: str,
        repository_url: str,
        repository_name: str,
        chart_path: str,
        cluster: Dict[str, Any],
        namespace: str,
        values_file: str,
        values_files: Optional[List[str]],
        cluster_values_map: Dict[str, str],
        set_values: Optional[List[str]],
        cluster_set_values_map: Dict[str, List[str]],
        wait: bool,
        timeout: str,
        atomic: bool,
        kubeconfig: str,
        helm_labels: Dict[str, str],
    ) -> List[str]:
        """Build Helm command with all parameters."""
        cmd = ["helm", operation]

        if operation in ["install", "upgrade"]:
            cmd.append(release_name)

            # Add chart source
            if chart_path:
                cmd.append(chart_path)
            elif repository_url:
                cmd.extend(["--repo", repository_url, chart_name])
            elif repository_name:
                cmd.append(f"{repository_name}/{chart_name}")
            else:
                cmd.append(chart_name)

            # Add chart version
            if chart_version:
                cmd.extend(["--version", chart_version])

            # Add values files
            if values_file:
                cmd.extend(["-f", values_file])

            if values_files:
                for vf in values_files:
                    cmd.extend(["-f", vf])

            # Add cluster-specific values
            cluster_specific_values = cluster_values_map.get(cluster["name"])
            if cluster_specific_values:
                cmd.extend(["-f", cluster_specific_values])

            # Add set values
            if set_values:
                for set_value in set_values:
                    cmd.extend(["--set", set_value])

            # Add cluster-specific set values
            cluster_specific_set_values = cluster_set_values_map.get(cluster["name"])
            if cluster_specific_set_values:
                for set_value in cluster_specific_set_values:
                    cmd.extend(["--set", set_value])

            # Add KubeStellar labels
            for key, value in helm_labels.items():
                cmd.extend(["--set", f"labels.{key}={value}"])

            # Add common parameters
            if wait:
                cmd.append("--wait")

            if timeout:
                cmd.extend(["--timeout", timeout])

            if atomic:
                cmd.append("--atomic")

            if operation == "upgrade":
                cmd.append("--install")  # Create if doesn't exist

        elif operation == "uninstall":
            cmd.append(release_name)

        # Add Kubernetes context and namespace
        cmd.extend(["--kube-context", cluster["context"]])
        cmd.extend(["--namespace", namespace])

        if kubeconfig:
            cmd.extend(["--kubeconfig", kubeconfig])

        return cmd

    async def _ensure_namespace_exists(
        self,
        cluster: Dict[str, Any],
        namespace: str,
        kubeconfig: str,
        labels: Dict[str, str],
    ) -> None:
        """Ensure namespace exists with proper labels."""
        # Check if namespace exists
        check_cmd = [
            "kubectl",
            "get",
            "namespace",
            namespace,
            "--context",
            cluster["context"],
        ]
        if kubeconfig:
            check_cmd.extend(["--kubeconfig", kubeconfig])

        result = await self._run_command(check_cmd)

        if result["returncode"] != 0:
            # Create namespace
            create_cmd = [
                "kubectl",
                "create",
                "namespace",
                namespace,
                "--context",
                cluster["context"],
            ]
            if kubeconfig:
                create_cmd.extend(["--kubeconfig", kubeconfig])

            await self._run_command(create_cmd)

        # Label namespace with KubeStellar labels
        for key, value in labels.items():
            label_cmd = [
                "kubectl",
                "label",
                "namespace",
                namespace,
                f"{key}={value}",
                "--context",
                cluster["context"],
                "--overwrite",
            ]
            if kubeconfig:
                label_cmd.extend(["--kubeconfig", kubeconfig])

            await self._run_command(label_cmd)

    async def _label_helm_secret(
        self,
        cluster: Dict[str, Any],
        namespace: str,
        release_name: str,
        labels: Dict[str, str],
        kubeconfig: str,
    ) -> None:
        """Label Helm secret for KubeStellar BindingPolicy compatibility."""
        try:
            # Get Helm secret name
            get_secret_cmd = [
                "kubectl",
                "get",
                "secrets",
                "--context",
                cluster["context"],
                "--namespace",
                namespace,
                "-l",
                f"name={release_name}",
                "-l",
                "owner=helm",
                "-o",
                "jsonpath={.items[0].metadata.name}",
            ]
            if kubeconfig:
                get_secret_cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(get_secret_cmd)

            if result["returncode"] == 0 and result["stdout"].strip():
                secret_name = result["stdout"].strip()

                # Label the Helm secret
                for key, value in labels.items():
                    label_cmd = [
                        "kubectl",
                        "label",
                        "secret",
                        secret_name,
                        f"{key}={value}",
                        "--context",
                        cluster["context"],
                        "--namespace",
                        namespace,
                        "--overwrite",
                    ]
                    if kubeconfig:
                        label_cmd.extend(["--kubeconfig", kubeconfig])

                    await self._run_command(label_cmd)

        except Exception:
            # Non-critical operation, continue if it fails
            pass

    async def _parse_helm_output(
        self,
        output: str,
        operation: str,
        release_name: str,
        cluster: Dict[str, Any],
        namespace: str,
        kubeconfig: str,
    ) -> Dict[str, Any]:
        """Parse Helm command output for release information."""
        info = {}

        try:
            # Get detailed release information
            status_cmd = [
                "helm",
                "status",
                release_name,
                "--kube-context",
                cluster["context"],
                "--namespace",
                namespace,
                "-o",
                "json",
            ]
            if kubeconfig:
                status_cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(status_cmd)

            if result["returncode"] == 0:
                status_data = json.loads(result["stdout"])
                info.update(
                    {
                        "release_name": status_data.get("name", release_name),
                        "revision": status_data.get("version", "unknown"),
                        "status": status_data.get("info", {}).get("status", "unknown"),
                        "chart_name": status_data.get("chart", {})
                        .get("metadata", {})
                        .get("name", ""),
                        "chart_version": status_data.get("chart", {})
                        .get("metadata", {})
                        .get("version", ""),
                        "app_version": status_data.get("chart", {})
                        .get("metadata", {})
                        .get("appVersion", ""),
                    }
                )

        except Exception:
            # Fallback to basic information
            info = {
                "release_name": release_name,
                "revision": "unknown",
                "status": (
                    "deployed" if operation in ["install", "upgrade"] else "unknown"
                ),
            }

        return info

    async def _uninstall_helm_chart(
        self,
        clusters: List[Dict[str, Any]],
        release_name: str,
        target_namespaces: List[str],
        kubeconfig: str,
    ) -> Dict[str, Any]:
        """Uninstall Helm chart from selected clusters."""
        results = {}

        for cluster in clusters:
            cluster_result = {"cluster": cluster["name"], "namespace_results": {}}

            for namespace in target_namespaces:
                cmd = [
                    "helm",
                    "uninstall",
                    release_name,
                    "--kube-context",
                    cluster["context"],
                    "--namespace",
                    namespace,
                ]
                if kubeconfig:
                    cmd.extend(["--kubeconfig", kubeconfig])

                result = await self._run_command(cmd)

                if result["returncode"] == 0:
                    cluster_result["namespace_results"][namespace] = {
                        "status": "success",
                        "output": result["stdout"],
                    }
                else:
                    error_output = result["stderr"] or result["stdout"]
                    cluster_result["namespace_results"][namespace] = {
                        "status": "error",
                        "error": f"Helm uninstall failed: {error_output}",
                        "output": error_output,
                    }

            # Determine overall cluster status
            success_count = sum(
                1
                for r in cluster_result["namespace_results"].values()
                if r["status"] == "success"
            )
            cluster_result["status"] = "success" if success_count > 0 else "error"

            results[cluster["name"]] = cluster_result

        success_count = sum(1 for r in results.values() if r["status"] == "success")

        return {
            "status": "success" if success_count > 0 else "error",
            "operation": "uninstall",
            "clusters_total": len(clusters),
            "clusters_succeeded": success_count,
            "clusters_failed": len(clusters) - success_count,
            "results": results,
        }

    async def _get_helm_info(
        self,
        clusters: List[Dict[str, Any]],
        release_name: str,
        target_namespaces: List[str],
        operation: str,
        kubeconfig: str,
    ) -> Dict[str, Any]:
        """Execute helm status/history commands across multiple clusters."""
        results = {}

        for cluster in clusters:
            cluster_result = {"cluster": cluster["name"], "namespace_results": {}}

            for namespace in target_namespaces:
                cmd = [
                    "helm",
                    operation,
                    release_name,
                    "--kube-context",
                    cluster["context"],
                    "--namespace",
                    namespace,
                ]

                if operation == "status":
                    cmd.extend(["-o", "json"])

                if kubeconfig:
                    cmd.extend(["--kubeconfig", kubeconfig])

                result = await self._run_command(cmd)

                if result["returncode"] == 0:
                    info = {"status": "success", "output": result["stdout"]}

                    # Parse JSON output for status operation
                    if operation == "status":
                        try:
                            status_data = json.loads(result["stdout"])
                            info.update(
                                {
                                    "release_info": {
                                        "name": status_data.get("name", release_name),
                                        "revision": status_data.get(
                                            "version", "unknown"
                                        ),
                                        "status": status_data.get("info", {}).get(
                                            "status", "unknown"
                                        ),
                                        "chart": status_data.get("chart", {}).get(
                                            "metadata", {}
                                        ),
                                        "last_deployed": status_data.get(
                                            "info", {}
                                        ).get("last_deployed", ""),
                                    }
                                }
                            )
                        except json.JSONDecodeError:
                            pass

                    cluster_result["namespace_results"][namespace] = info
                else:
                    error_output = result["stderr"] or result["stdout"]
                    cluster_result["namespace_results"][namespace] = {
                        "status": "error",
                        "error": f"Helm {operation} failed: {error_output}",
                        "output": error_output,
                    }

            # Determine overall cluster status
            success_count = sum(
                1
                for r in cluster_result["namespace_results"].values()
                if r["status"] == "success"
            )
            cluster_result["status"] = "success" if success_count > 0 else "error"

            results[cluster["name"]] = cluster_result

        success_count = sum(1 for r in results.values() if r["status"] == "success")

        return {
            "status": "success" if success_count > 0 else "error",
            "operation": operation,
            "clusters_total": len(clusters),
            "clusters_succeeded": success_count,
            "clusters_failed": len(clusters) - success_count,
            "results": results,
        }

    async def _create_binding_policy(
        self,
        policy_name: str,
        release_name: str,
        helm_labels: Dict[str, str],
        cluster_selector_labels: Optional[Dict[str, str]],
        target_namespaces: List[str],
        wds_context: str,
        kubeconfig: str,
    ) -> Dict[str, Any]:
        """Create KubeStellar binding policy for Helm deployment."""
        try:
            # Prepare cluster selectors
            cluster_selectors = []
            if cluster_selector_labels:
                cluster_selectors.append({"matchLabels": cluster_selector_labels})
            else:
                # Default cluster selector for edge clusters
                cluster_selectors.append({"matchLabels": {"location-group": "edge"}})

            # Prepare object selectors for Helm-managed resources
            object_selectors = [
                {
                    "matchLabels": {
                        "app.kubernetes.io/managed-by": "Helm",
                        "app.kubernetes.io/instance": release_name,
                    }
                }
            ]

            # Add additional labels if specified
            if helm_labels:
                additional_selector: Dict[str, Any] = {"matchLabels": {}}
                for key, value in helm_labels.items():
                    if key not in [
                        "app.kubernetes.io/managed-by",
                        "app.kubernetes.io/instance",
                    ]:
                        additional_selector["matchLabels"][key] = value

                if additional_selector["matchLabels"]:
                    object_selectors.append(additional_selector)

            # Create binding policy YAML
            binding_policy = {
                "apiVersion": "control.kubestellar.io/v1alpha1",
                "kind": "BindingPolicy",
                "metadata": {
                    "name": policy_name,
                    "labels": {
                        "kubestellar.io/helm-chart": helm_labels.get(
                            "kubestellar.io/helm-chart", release_name
                        ),
                        "kubestellar.io/helm-release": release_name,
                    },
                },
                "spec": {
                    "clusterSelectors": cluster_selectors,
                    "downsync": [{"objectSelectors": object_selectors}],
                },
            }

            # Write binding policy to temporary file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(binding_policy, f, default_flow_style=False)
                policy_file = f.name

            # Apply binding policy to WDS context
            apply_cmd = ["kubectl", "apply", "-f", policy_file]

            if wds_context:
                apply_cmd.extend(["--context", wds_context])

            if kubeconfig:
                apply_cmd.extend(["--kubeconfig", kubeconfig])

            result = await self._run_command(apply_cmd)

            # Cleanup temporary file
            import os

            os.unlink(policy_file)

            if result["returncode"] == 0:
                return {
                    "status": "success",
                    "policy_name": policy_name,
                    "policy_spec": binding_policy["spec"],
                    "output": result["stdout"],
                }
            else:
                return {
                    "status": "error",
                    "policy_name": policy_name,
                    "error": f"Failed to create binding policy: {result['stderr'] or result['stdout']}",
                }

        except Exception as e:
            return {
                "status": "error",
                "policy_name": policy_name,
                "error": f"Failed to create binding policy: {str(e)}",
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

        return all_clusters

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

                # Skip WDS (Workload Description Space) clusters for direct deployment
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

    def _is_its_cluster(self, cluster_name: str) -> bool:
        """Check if cluster is an ITS (Inventory & Template Space) cluster."""
        lower_name = cluster_name.lower()
        return (
            lower_name.startswith("its")
            or "-its-" in lower_name
            or "_its_" in lower_name
        )

    def _is_wec_cluster(self, cluster_name: str) -> bool:
        """Check if cluster is a WEC (Workload Execution Cluster)."""
        # WEC clusters are typically named cluster1, cluster2, etc.
        # They are not WDS or ITS clusters
        return not (
            self._is_wds_cluster(cluster_name) or self._is_its_cluster(cluster_name)
        )

    def _log_warning(self, message: str) -> None:
        """Log a warning message."""
        import sys

        print(f"WARNING: {message}", file=sys.stderr)

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
                "chart_name": {
                    "type": "string",
                    "description": "Name of the Helm chart (e.g., nginx-ingress, prometheus)",
                },
                "chart_version": {
                    "type": "string",
                    "description": "Version of the chart to deploy",
                },
                "repository_url": {
                    "type": "string",
                    "description": "Helm repository URL (e.g., https://kubernetes.github.io/ingress-nginx)",
                },
                "repository_name": {
                    "type": "string",
                    "description": "Helm repository name (if already added to local repos)",
                },
                "chart_path": {
                    "type": "string",
                    "description": "Local path to chart directory or .tgz file",
                },
                "release_name": {
                    "type": "string",
                    "description": "Name of the Helm release (defaults to chart name)",
                },
                "target_clusters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Names of specific clusters to deploy to",
                },
                "cluster_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Label selectors for cluster targeting in key=value format",
                },
                "namespace": {
                    "type": "string",
                    "description": "Target namespace for deployment",
                    "default": "default",
                },
                "all_namespaces": {
                    "type": "boolean",
                    "description": "Deploy across all namespaces",
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
                "values_file": {
                    "type": "string",
                    "description": "Path to values file",
                },
                "values_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of values files",
                },
                "cluster_values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Per-cluster values files in cluster=values.yaml format",
                },
                "set_values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Set values in key=value format",
                },
                "cluster_set_values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Per-cluster set values in cluster=key=value format",
                },
                "create_namespace": {
                    "type": "boolean",
                    "description": "Create namespace if it doesn't exist",
                    "default": True,
                },
                "wait": {
                    "type": "boolean",
                    "description": "Wait for deployment to complete",
                    "default": True,
                },
                "timeout": {
                    "type": "string",
                    "description": "Deployment timeout (e.g., 5m, 300s)",
                    "default": "5m",
                },
                "atomic": {
                    "type": "boolean",
                    "description": "Atomic deployment (rollback on failure)",
                    "default": False,
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Perform dry run without actual deployment",
                    "default": False,
                },
                "operation": {
                    "type": "string",
                    "description": "Helm operation to perform",
                    "enum": ["install", "upgrade", "uninstall", "status", "history"],
                    "default": "install",
                },
                "kubeconfig": {
                    "type": "string",
                    "description": "Path to kubeconfig file",
                },
                "remote_context": {
                    "type": "string",
                    "description": "Remote context for cluster discovery",
                },
                "create_binding_policy": {
                    "type": "boolean",
                    "description": "Create KubeStellar binding policy for the deployment",
                    "default": True,
                },
                "binding_policy_name": {
                    "type": "string",
                    "description": "Name for the binding policy (defaults to release-name-helm-policy)",
                },
                "cluster_selector_labels": {
                    "type": "object",
                    "description": "Labels for cluster selection in binding policy",
                    "additionalProperties": {"type": "string"},
                },
                "kubestellar_labels": {
                    "type": "object",
                    "description": "Additional KubeStellar labels for resources",
                    "additionalProperties": {"type": "string"},
                },
                "wds_context": {
                    "type": "string",
                    "description": "WDS (Workload Description Space) context for binding policy creation",
                },
            },
            "anyOf": [
                {
                    "allOf": [
                        {"required": ["operation"]},
                        {"properties": {"operation": {"const": "install"}}},
                        {
                            "anyOf": [
                                {"required": ["chart_name"]},
                                {"required": ["chart_path"]},
                            ]
                        },
                    ]
                },
                {
                    "allOf": [
                        {"required": ["operation"]},
                        {"properties": {"operation": {"const": "upgrade"}}},
                        {
                            "anyOf": [
                                {"required": ["chart_name"]},
                                {"required": ["chart_path"]},
                            ]
                        },
                    ]
                },
                {
                    "allOf": [
                        {"required": ["operation"]},
                        {
                            "properties": {
                                "operation": {
                                    "enum": ["uninstall", "status", "history"]
                                }
                            }
                        },
                        {
                            "anyOf": [
                                {"required": ["release_name"]},
                                {"required": ["chart_name"]},
                            ]
                        },
                    ]
                },
            ],
        }
