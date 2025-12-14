"""Vanilla Kubernetes provider implementation."""

from __future__ import annotations

import json
from typing import Iterable

from src.shared.providers.base import ClusterContext, ClusterProvider, ProviderMode
from src.shared.utils import run_shell_command_with_cancellation


class KubernetesProvider(ClusterProvider):
    mode = ProviderMode.KUBERNETES

    def describe(self) -> str:
        return "Standard Kubernetes cluster"

    async def discover_clusters(self, kubeconfig: str | None = None) -> Iterable[ClusterContext]:
        cmd = ["kubectl", "config", "get-contexts", "-o", "json"]
        if kubeconfig:
            cmd += ["--kubeconfig", kubeconfig]
        result = await run_shell_command_with_cancellation(cmd)
        if result["returncode"] != 0:
            return []
        data = json.loads(result["stdout"] or "{}")
        contexts = []
        for ctx in data.get("contexts", []):
            name = ctx.get("name")
            if not name:
                continue
            # Filter obvious KubeStellar contexts so we don't double expose them
            if any(sub in name.lower() for sub in ("wds", "its", "kubestellar")):
                continue
            contexts.append(
                ClusterContext(
                    name=name,
                    context=name,
                    labels={},
                    is_kubestellar=False,
                )
            )
        return contexts

    def supports_function(self, function_name: str) -> bool:
        kubestellar_only = {
            "kubestellar_management",
            "binding_policy_management",
            "multicluster_create",
            "multicluster_logs",
        }
        return function_name not in kubestellar_only
