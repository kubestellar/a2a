from __future__ import annotations

import asyncio, json
from typing import Any, Dict, List

from src.shared.base_functions import BaseFunction


class ClusterLabelManagement(BaseFunction):
    """
    Add / update labels on an Open-Cluster-Management ManagedCluster.

    Typical call:
        • cluster_name  – managedcluster resource name
        • labels        – dict of key → value
        • kube_context  – context of the OCM Hub / ITS (default: its1)
    """

    def __init__(self) -> None:
        super().__init__(
            name="cluster_label_management",
            description="Add or update labels on a ManagedCluster object."
        )

    # ────────────────────────── public entry ──────────────────────────
    async def execute(
        self,
        cluster_name: str,
        labels: Dict[str, str] | None = None,
        remove_labels: List[str] | None = None,
        kube_context: str = "its1",        # default is ITS / OCM hub
        kubeconfig: str = "",
        **_: Any,
    ) -> Dict[str, Any]:
        if not cluster_name:
            return {"status": "error", "error": "cluster_name is required"}
        if not labels and not remove_labels:
            return {"status": "error", "error": "labels or remove_labels must be provided"}

        label_args: List[str] = []
        if labels:
            label_args += [f"{k}={v}" for k, v in labels.items()]
        if remove_labels:
            label_args += [f"{key}-" for key in remove_labels]
        cmd = [
            "kubectl", "--context", kube_context,
            "label", "managedcluster", cluster_name,
            *label_args, "--overwrite",
        ]
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            # Surface full stderr so the LLM can show the exact cause
            return {
                "status": "error",
                "stderr": stderr.decode().strip(),
                "cmd": " ".join(cmd),
            }

        return {
            "status": "success",
            "stdout": stdout.decode().strip(),
            "cmd": " ".join(cmd),
        }

    # ────────────────────────── JSON schema ──────────────────────────
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "cluster_name": {
                    "type": "string",
                    "description": "Name of the ManagedCluster resource",
                },
                "labels": {
                    "type": "object",
                    "description": "Dictionary of label key/value pairs to add/update",
                },
                "remove_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of label keys to delete",
                },
                "kube_context": {
                    "type": "string",
                    "description": "kubectl context of the OCM hub",
                    "default": "its1",
                },
                "kubeconfig": {
                    "type": "string",
                    "description": "Path to alternate kubeconfig (optional)",
                },
            },
            "required": ["cluster_name"],
        }