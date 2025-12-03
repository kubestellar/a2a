"""Cluster management function for KubeStellar.

Provides cluster registration, labeling, and management capabilities:
- Register clusters with WDS context
- Apply labels to clusters
- List registered clusters
- Remove clusters from WDS context
- Update cluster labels
"""

import json
from typing import Any, Dict, Optional

from src.shared.base_functions import BaseFunction
from src.shared.utils import run_shell_command_with_cancellation


class ClusterManagementFunction(BaseFunction):
    """Manage KubeStellar clusters with registration and labeling capabilities."""

    def __init__(self) -> None:
        super().__init__(
            name="cluster_management",
            description="Register and manage clusters in KubeStellar WDS context. Apply labels, list registered clusters, and manage cluster metadata.",
        )

    async def execute(
        self,
        operation: str = "list",
        cluster_name: str = "",
        context: str = "wds1",
        labels: Optional[Dict[str, str]] = None,
        kubeconfig: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute cluster management operations.

        Args:
            operation (str): Operation to perform
                Options: 'list', 'register', 'label', 'unregister', 'update-labels'
                Default: 'list'
                - 'list': List all registered clusters in WDS context
                - 'register': Register a new cluster with WDS context
                - 'label': Apply labels to a registered cluster
                - 'unregister': Remove a cluster from WDS context
                - 'update-labels': Update existing labels on a cluster

            cluster_name (str): Name of the cluster to manage
                Required for register, label, unregister, update-labels operations
                Example: 'cluster1', 'cluster2'

            context (str): Kubernetes context name
                The context where clusters are registered (WDS or ITS)
                Default: 'wds1'
                Example: 'wds1', 'wds2', 'its1'

            labels (Dict[str, str]): Labels to apply to the cluster
                Used for register, label, and update-labels operations
                Example: {'environment': 'prod', 'region': 'us-west'}

            kubeconfig (str, optional): Path to kubeconfig file
                Uses default kubeconfig if not specified
                Example: '/path/to/kubeconfig'

        Returns:
            Dict[str, Any]: Operation result containing:
                - status: 'success' or 'error'
                - operation: Type of operation performed
                - clusters: List of registered clusters (for list operation)
                - cluster_info: Detailed cluster information
                - error: Error message if status='error'

        Examples:
            # List all registered clusters
            >>> cluster_management(operation='list')

            # Register a cluster with labels
            >>> cluster_management(
            ...     operation='register',
            ...     cluster_name='cluster1',
            ...     labels={'environment': 'prod', 'region': 'us-west'}
            ... )

            # Apply labels to existing cluster
            >>> cluster_management(
            ...     operation='label',
            ...     cluster_name='cluster2',
            ...     labels={'environment': 'prod', 'region': 'us-east'}
            ... )
        """
        try:
            # Convert MapComposite objects to regular dicts/lists
            def _convert_mapcomposite(obj):
                """Convert protobuf MapComposite objects to regular Python dicts/lists"""
                if obj is None:
                    return obj
                elif hasattr(obj, "items") and callable(getattr(obj, "items")):
                    return dict(obj.items())
                elif hasattr(obj, "__iter__") and not isinstance(
                    obj, (str, dict, bytes)
                ):
                    return list(obj)
                return obj

            # Convert all parameters that might contain MapComposite objects
            labels = _convert_mapcomposite(labels)

            if operation == "list":
                return await self._list_clusters(context, kubeconfig)
            elif operation == "register":
                if not cluster_name:
                    return {
                        "status": "error",
                        "error": "cluster_name is required for register operation",
                    }
                return await self._register_cluster(
                    cluster_name, context, labels or {}, kubeconfig
                )
            elif operation == "label":
                if not cluster_name:
                    return {
                        "status": "error",
                        "error": "cluster_name is required for label operation",
                    }
                if not labels:
                    return {
                        "status": "error",
                        "error": "labels are required for label operation",
                    }
                return await self._label_cluster(
                    cluster_name, context, labels, kubeconfig
                )
            elif operation == "unregister":
                if not cluster_name:
                    return {
                        "status": "error",
                        "error": "cluster_name is required for unregister operation",
                    }
                return await self._unregister_cluster(cluster_name, context, kubeconfig)
            elif operation == "update-labels":
                if not cluster_name:
                    return {
                        "status": "error",
                        "error": "cluster_name is required for update-labels operation",
                    }
                if not labels:
                    return {
                        "status": "error",
                        "error": "labels are required for update-labels operation",
                    }
                return await self._update_labels(
                    cluster_name, context, labels, kubeconfig
                )
            else:
                return {"status": "error", "error": f"unknown operation: {operation}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _list_clusters(self, context: str, kubeconfig: str) -> Dict[str, Any]:
        """List all registered clusters in the context."""
        # For ITS context, list ManagedClusters
        if "its" in context.lower():
            cmd = [
                "kubectl",
                "--context",
                context,
                "get",
                "managedclusters",
                "-o",
                "json",
            ]
        else:
            # For WDS context, list Bindings
            cmd = [
                "kubectl",
                "--context",
                context,
                "get",
                "bindings.control.kubestellar.io",
                "-o",
                "json",
            ]

        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]

        ret = await run_shell_command_with_cancellation(cmd)
        if ret["returncode"] != 0:
            return {"status": "error", "error": ret["stderr"]}

        if "its" in context.lower():
            # Parse ManagedClusters
            managed_clusters = json.loads(ret["stdout"]).get("items", [])
            clusters = []
            for mc in managed_clusters:
                clusters.append(
                    {
                        "name": mc["metadata"]["name"],
                        "labels": mc["metadata"].get("labels", {}),
                        "created": mc["metadata"]["creationTimestamp"],
                    }
                )
        else:
            # Parse Bindings (original logic)
            bindings = json.loads(ret["stdout"]).get("items", [])
            clusters = []

            for binding in bindings:
                for dest in binding.get("spec", {}).get("destinations", []):
                    cluster_id = dest.get("clusterId")
                    if cluster_id:
                        clusters.append(
                            {
                                "name": cluster_id,
                                "binding": binding["metadata"]["name"],
                                "created": binding["metadata"]["creationTimestamp"],
                            }
                        )

        return {
            "status": "success",
            "operation": "list",
            "total": len(clusters),
            "clusters": clusters,
        }

    async def _register_cluster(
        self, cluster_name: str, context: str, labels: Dict[str, str], kubeconfig: str
    ) -> Dict[str, Any]:
        """Register a cluster with the context. For WEC clusters, use ITS context."""
        # Check if cluster is already registered
        list_result = await self._list_clusters(context, kubeconfig)
        if list_result["status"] == "success":
            for cluster in list_result["clusters"]:
                if cluster["name"] == cluster_name:
                    return {
                        "status": "error",
                        "error": f"Cluster '{cluster_name}' is already registered",
                    }

        # For WEC clusters registered to ITS, create ManagedCluster manifest
        if "its" in context.lower():
            # Create ManagedCluster for WEC registration
            managed_cluster_manifest = {
                "apiVersion": "cluster.open-cluster-management.io/v1",
                "kind": "ManagedCluster",
                "metadata": {"name": cluster_name, "labels": labels},
                "spec": {"hubAcceptsClient": True},
            }

            # Apply the ManagedCluster
            import yaml

            manifest_yaml = yaml.safe_dump(managed_cluster_manifest, sort_keys=False)
            cmd = ["kubectl", "--context", context, "apply", "-f", "-"]
            if kubeconfig:
                cmd += ["--kubeconfig", kubeconfig]

            import subprocess

            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate(input=manifest_yaml)

            if process.returncode == 0:
                return {
                    "status": "success",
                    "operation": "register",
                    "cluster_name": cluster_name,
                    "context": context,
                    "labels": labels,
                    "message": f"Successfully registered cluster '{cluster_name}' to {context}",
                }
            else:
                return {
                    "status": "error",
                    "error": f"Failed to register cluster: {stderr}",
                }

        # Original Binding creation for WDS context
        binding_name = f"{cluster_name}-binding"
        binding_manifest = {
            "apiVersion": "control.kubestellar.io/v1alpha1",
            "kind": "Binding",
            "metadata": {"name": binding_name, "labels": labels},
            "spec": {"destinations": [{"clusterId": cluster_name}], "workload": {}},
        }

        # Apply the binding
        import yaml

        binding_yaml = yaml.safe_dump(binding_manifest, sort_keys=False)
        cmd = ["kubectl", "--context", context, "apply", "-f", "-"]
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]

        ret = await run_shell_command_with_cancellation(
            cmd, input_data=binding_yaml.encode()
        )
        if ret["returncode"] != 0:
            return {"status": "error", "error": ret["stderr"]}

        # Apply labels to the cluster nodes (if possible)
        try:
            await self._apply_cluster_labels(cluster_name, labels, kubeconfig)
        except Exception:
            # Ignore labeling errors - the binding is the important part
            pass

        return {
            "status": "success",
            "operation": "register",
            "cluster": cluster_name,
            "binding": binding_name,
            "labels": labels,
        }

    async def _label_cluster(
        self, cluster_name: str, context: str, labels: Dict[str, str], kubeconfig: str
    ) -> Dict[str, Any]:
        """Apply labels to a registered cluster."""
        # Update the binding with new labels
        cmd = [
            "kubectl",
            "--context",
            context,
            "label",
            "bindings.control.kubestellar.io",
            f"{cluster_name}-binding",
        ]
        for k, v in labels.items():
            cmd.append(f"{k}={v}")
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]

        ret = await run_shell_command_with_cancellation(cmd)
        if ret["returncode"] != 0:
            return {"status": "error", "error": ret["stderr"]}

        # Also try to apply labels to cluster nodes
        try:
            await self._apply_cluster_labels(cluster_name, labels, kubeconfig)
        except Exception:
            pass

        return {
            "status": "success",
            "operation": "label",
            "cluster": cluster_name,
            "labels": labels,
        }

    async def _update_labels(
        self, cluster_name: str, context: str, labels: Dict[str, str], kubeconfig: str
    ) -> Dict[str, Any]:
        """Update labels on a registered cluster."""
        # First, get current labels
        cmd = [
            "kubectl",
            "--context",
            context,
            "get",
            "bindings.control.kubestellar.io",
            f"{cluster_name}-binding",
            "-o",
            "json",
        ]
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]

        ret = await run_shell_command_with_cancellation(cmd)
        if ret["returncode"] != 0:
            return {"status": "error", "error": ret["stderr"]}

        binding = json.loads(ret["stdout"])
        current_labels = binding.get("metadata", {}).get("labels", {})

        # Update labels (remove existing and add new)
        cmd = [
            "kubectl",
            "--context",
            context,
            "label",
            "bindings.control.kubestellar.io",
            f"{cluster_name}-binding",
        ]
        # Remove existing labels
        for key in current_labels:
            cmd.append(f"{key}-")
        # Add new labels
        for k, v in labels.items():
            cmd.append(f"{k}={v}")
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]

        ret = await run_shell_command_with_cancellation(cmd)
        if ret["returncode"] != 0:
            return {"status": "error", "error": ret["stderr"]}

        # Also try to apply labels to cluster nodes
        try:
            await self._apply_cluster_labels(cluster_name, labels, kubeconfig)
        except Exception:
            pass

        return {
            "status": "success",
            "operation": "update-labels",
            "cluster": cluster_name,
            "old_labels": current_labels,
            "new_labels": labels,
        }

    async def _unregister_cluster(
        self, cluster_name: str, context: str, kubeconfig: str
    ) -> Dict[str, Any]:
        """Remove a cluster from the WDS context."""
        binding_name = f"{cluster_name}-binding"
        cmd = [
            "kubectl",
            "--context",
            context,
            "delete",
            "bindings.control.kubestellar.io",
            binding_name,
        ]
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]

        ret = await run_shell_command_with_cancellation(cmd)
        if ret["returncode"] != 0:
            return {"status": "error", "error": ret["stderr"]}

        return {
            "status": "success",
            "operation": "unregister",
            "cluster": cluster_name,
            "binding": binding_name,
        }

    async def _apply_cluster_labels(
        self, cluster_name: str, labels: Dict[str, str], kubeconfig: str
    ) -> Dict[str, Any]:
        """Apply labels to cluster nodes."""
        # Get nodes in the cluster
        cmd = ["kubectl", "--context", cluster_name, "get", "nodes", "-o", "json"]
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]

        ret = await run_shell_command_with_cancellation(cmd)
        if ret["returncode"] != 0:
            raise Exception(f"Failed to get nodes: {ret['stderr']}")

        nodes = json.loads(ret["stdout"]).get("items", [])

        # Apply labels to each node
        for node in nodes:
            node_name = node["metadata"]["name"]
            cmd = ["kubectl", "--context", cluster_name, "label", "node", node_name]
            for k, v in labels.items():
                cmd.append(f"{k}={v}")
            if kubeconfig:
                cmd += ["--kubeconfig", kubeconfig]

            ret = await run_shell_command_with_cancellation(cmd)
            if ret["returncode"] != 0:
                # Continue with other nodes even if one fails
                continue

        return {"status": "success"}

    def get_schema(self) -> Dict[str, Any]:
        """Define the JSON schema for function parameters."""
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "Operation to perform: list, register, label, unregister, update-labels",
                    "enum": [
                        "list",
                        "register",
                        "label",
                        "unregister",
                        "update-labels",
                    ],
                    "default": "list",
                },
                "cluster_name": {
                    "type": "string",
                    "description": "Name of the cluster to manage (required for most operations)",
                },
                "context": {
                    "type": "string",
                    "description": "Kubernetes context name where clusters are registered (WDS or ITS)",
                    "default": "wds1",
                },
                "labels": {
                    "type": "object",
                    "description": "Labels to apply to the cluster (key-value pairs)",
                    "additionalProperties": {"type": "string"},
                },
                "kubeconfig": {
                    "type": "string",
                    "description": "Path to kubeconfig file",
                },
            },
            "required": ["operation"],
        }
