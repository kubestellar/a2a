"""Registry for cluster providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from src.shared.providers.base import ClusterProvider, ProviderMode


@dataclass
class ProviderEntry:
    provider: ClusterProvider
    supports_default: bool = False


class ProviderRegistry:
    """Singleton registry for providers."""

    def __init__(self):
        self._providers: Dict[ProviderMode, ProviderEntry] = {}

    def register(
        self, provider: ClusterProvider, *, supports_default: bool = False
    ) -> None:
        self._providers[provider.mode] = ProviderEntry(
            provider=provider, supports_default=supports_default
        )

    def get(self, mode: ProviderMode) -> Optional[ClusterProvider]:
        entry = self._providers.get(mode)
        return entry.provider if entry else None

    def default_mode(self) -> ProviderMode:
        for mode, entry in self._providers.items():
            if entry.supports_default:
                return mode
        raise RuntimeError("No default provider registered")

    def available_modes(self) -> Iterable[ProviderMode]:
        return self._providers.keys()

    def has_mode(self, mode: ProviderMode) -> bool:
        return mode in self._providers


_REGISTRY: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ProviderRegistry()
    return _REGISTRY


def ensure_default_providers() -> ProviderRegistry:
    """Register built-in providers if none are registered yet."""

    registry = get_provider_registry()
    if not any(True for _ in registry.available_modes()):
        from src.shared.providers.kubernetes import KubernetesProvider
        from src.shared.providers.kubestellar import KubeStellarProvider

        registry.register(KubernetesProvider(), supports_default=True)
        registry.register(KubeStellarProvider())

    return registry
