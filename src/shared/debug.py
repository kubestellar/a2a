"""Runtime-configurable debug logging utilities."""

from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator

_logger = logging.getLogger("kubestellar")
_state_lock = threading.Lock()
_enabled = False


def configure_root(level: int = logging.INFO) -> None:
    """Ensure standard logging configuration is present."""

    if not logging.getLogger().handlers:
        logging.basicConfig(level=level)


def is_enabled() -> bool:
    """Return whether verbose debug logging is active."""

    with _state_lock:
        return _enabled


def enable() -> None:
    """Enable verbose logging globally."""

    global _enabled
    with _state_lock:
        _enabled = True
    _logger.setLevel(logging.DEBUG)
    _logger.debug("Verbose debug mode enabled")


def disable() -> None:
    """Disable verbose logging globally."""

    global _enabled
    with _state_lock:
        _enabled = False
    _logger.setLevel(logging.INFO)
    _logger.debug("Verbose debug mode disabled")


@contextmanager
def temporary_enable() -> Iterator[None]:
    """Temporarily enable verbose logging within a block."""

    was_enabled = is_enabled()
    if not was_enabled:
        enable()
    try:
        yield
    finally:
        if not was_enabled:
            disable()


def _normalise(payload: Dict[str, Any]) -> str:
    try:
        return json.dumps(payload, separators=(",", ":"))
    except TypeError:
        return str(payload)


def log_request(context: str, payload: Dict[str, Any]) -> None:
    """Emit structured debug log for outgoing requests."""

    if not is_enabled():
        return
    logging.getLogger("kubestellar.request").debug(
        "%s request: %s", context, _normalise(payload)
    )


def log_response(context: str, payload: Dict[str, Any]) -> None:
    """Emit structured debug log for responses."""

    if not is_enabled():
        return
    logging.getLogger("kubestellar.response").debug(
        "%s response: %s", context, _normalise(payload)
    )
