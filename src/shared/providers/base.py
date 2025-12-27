"""Provider interfaces shared across CLI and agent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Optional, Protocol


class ProviderMode(str, Enum):
    """Supported backend modes."""

    KUBESTELLAR = "kubestellar"
    KUBERNETES = "kubernetes"


@dataclass
class ClusterContext:
    """Minimal context information about a cluster target."""

    name: str
    context: str
    labels: Dict[str, str]
    api_endpoint: Optional[str] = None
    is_kubestellar: bool = False


class ClusterProvider(Protocol):
    """Abstraction for cluster discovery and capability checks."""

    mode: ProviderMode

    def describe(self) -> str:
        """Human readable description of the provider."""

    async def discover_clusters(self, kubeconfig: str | None = None) -> Iterable[ClusterContext]:
        """Return a list of clusters for the active mode."""

    def supports_function(self, function_name: str) -> bool:
        """Return whether a function should be exposed in this mode."""
