"""Serialization helpers for passing context and messages efficiently."""

from __future__ import annotations

import gzip
import json
from typing import Any, Dict


def to_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def from_json(text: str) -> Dict[str, Any]:
    return json.loads(text)


def to_compressed_bytes(data: Dict[str, Any]) -> bytes:
    return gzip.compress(to_json(data).encode("utf-8"))


def from_compressed_bytes(blob: bytes) -> Dict[str, Any]:
    return json.loads(gzip.decompress(blob).decode("utf-8"))


