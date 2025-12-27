"""Provider mode detection utilities."""

from __future__ import annotations

import json
import shutil
import subprocess

from src.shared.providers.base import ProviderMode
from src.shared.providers.registry import ensure_default_providers


def detect_mode(kubeconfig: str | None = None) -> ProviderMode:
    """Infer the provider mode based on cluster capabilities."""

    registry = ensure_default_providers()

    if not shutil.which("kubectl"):
        return registry.default_mode()

    cmd = [
        "kubectl",
        "get",
        "bindings.control.kubestellar.io",
        "-o",
        "json",
    ]
    if kubeconfig:
        cmd += ["--kubeconfig", kubeconfig]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return registry.default_mode()

    if result.returncode == 0:
        try:
            data = json.loads(result.stdout or "{}")
            if data.get("items"):
                return ProviderMode.KUBESTELLAR
        except json.JSONDecodeError:
            pass

    if registry.has_mode(ProviderMode.KUBERNETES):
        return ProviderMode.KUBERNETES
    return registry.default_mode()
