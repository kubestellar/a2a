"""Provider registry for managing LLM providers."""

from typing import Dict, Optional, Type

from .base import BaseLLMProvider, ProviderConfig

_provider_registry: Dict[str, Type[BaseLLMProvider]] = {}
_provider_instances: Dict[str, BaseLLMProvider] = {}


def register_provider(name: str, provider_class: Type[BaseLLMProvider]) -> None:
    """Register a provider class."""
    _provider_registry[name.lower()] = provider_class


def get_provider(name: str, config: Optional[ProviderConfig] = None) -> BaseLLMProvider:
    """
    Get or create a provider instance.

    Args:
        name: Provider name (e.g., 'gemini', 'claude')
        config: Provider configuration (required for first instantiation)

    Returns:
        Provider instance
    """
    name_lower = name.lower()

    # Check if instance already exists
    if name_lower in _provider_instances:
        return _provider_instances[name_lower]

    # Create new instance
    if name_lower not in _provider_registry:
        raise ValueError(
            f"Unknown provider: {name}. Available: {list(_provider_registry.keys())}"
        )

    if config is None:
        raise ValueError(f"Config required for first instantiation of {name}")

    provider_class = _provider_registry[name_lower]
    instance = provider_class(config)
    _provider_instances[name_lower] = instance

    return instance


def list_providers() -> list[str]:
    """List all registered providers."""
    return list(_provider_registry.keys())


def clear_providers() -> None:
    """Clear all provider instances (useful for testing)."""
    _provider_instances.clear()
