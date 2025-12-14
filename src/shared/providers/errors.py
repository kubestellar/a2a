"""Shared provider errors."""


class ProviderNotFoundError(RuntimeError):
    """Raised when the desired provider mode is not registered."""

