"""KubeStellar-specific provider implementation."""

from __future__ import annotations

import json
from typing import Iterable

from src.shared.providers.base import ClusterContext, ClusterProvider, ProviderMode
from src.shared.utils import run_shell_command_with_cancellation


class KubeStellarProvider(ClusterProvider):
    mode = ProviderMode.KUBESTELLAR

    def describe(self) -> str:
        return "KubeStellar multi-cluster control plane"

    async def discover_clusters(self, kubeconfig: str | None = None) -> Iterable[ClusterContext]:
        cmd = ["kubectl", "get", "bindings.control.kubestellar.io", "-o", "json"]
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]
        result = await run_shell_command_with_cancellation(cmd)
        if result["returncode"] != 0:
            return []
        data = json.loads(result["stdout"] or "{}")
        contexts = []
        for item in data.get("items", []):
            for dest in item.get("spec", {}).get("destinations", []):
                cluster_id = dest.get("clusterId")
                if cluster_id:
                    contexts.append(
                        ClusterContext(
                            name=cluster_id,
                            context=cluster_id,
                            labels=item.get("metadata", {}).get("labels", {}),
                            is_kubestellar=True,
                        )
                    )
        return contexts

    def supports_function(self, function_name: str) -> bool:
        return True  # All existing functions assume KubeStellar today
