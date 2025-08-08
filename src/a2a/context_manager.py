"""Global accessors for shared A2A context and broker."""

from __future__ import annotations

from typing import Optional

from .broker import A2ABroker
from .context import SharedContext

_shared_context: Optional[SharedContext] = None
_broker: Optional[A2ABroker] = None


def set_shared_context(ctx: SharedContext) -> None:
    global _shared_context
    _shared_context = ctx


def get_shared_context() -> SharedContext:
    global _shared_context
    if _shared_context is None:
        _shared_context = SharedContext()
    return _shared_context


def set_broker(b: A2ABroker) -> None:
    global _broker
    _broker = b


def get_broker() -> A2ABroker:
    global _broker
    if _broker is None:
        _broker = A2ABroker()
    return _broker


