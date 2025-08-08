"""Function to export current KubeStellar context to A2A shared context.

This function serializes the latest results from `kubestellar_management` into
the compact shared context used for AI-to-AI coordination and MCP prompts.
"""

from __future__ import annotations

from typing import Any, Dict

from ..base_functions import BaseFunction
from ...a2a.context_manager import get_shared_context
from ...a2a.context import ClusterSnapshot


class ExportKubeStellarContextFunction(BaseFunction):
    def __init__(self) -> None:
        super().__init__(
            name="export_kubestellar_context",
            description="Serialize and publish a compact multi-cluster context snapshot for A2A and MCP use",
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        ctx = get_shared_context()
        # Optionally accept a precomputed map from caller
        cluster_results = kwargs.get("cluster_results")
        if isinstance(cluster_results, dict):
            for cluster_name, data in cluster_results.items():
                snapshot = ClusterSnapshot(
                    name=cluster_name,
                    cluster_type=data.get("cluster_type", "unknown"),
                    resources_by_type=data.get("resources_by_type", {}),
                    kubestellar_resources=data.get("kubestellar_resources", []),
                )
                ctx.update_cluster(snapshot)

        delta = ctx.get_delta_if_changed()
        return {"status": "success", "delta": delta}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "cluster_results": {
                    "type": "object",
                    "description": "Optional results to merge into shared context (map of cluster -> result)",
                }
            },
        }


