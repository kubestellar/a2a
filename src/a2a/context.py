"""Shared context manager for multi-cluster state snapshots.

Provides serialization/deserialization and efficient delta updates for passing
cluster state to models and between agents.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ClusterSnapshot:
    name: str
    cluster_type: str
    resources_by_type: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    kubestellar_resources: List[Dict[str, Any]] = field(default_factory=list)
    updated_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_compact(self) -> Dict[str, Any]:
        return {
            "n": self.name,
            "t": self.cluster_type,
            "r": self.resources_by_type,
            "k": self.kubestellar_resources,
            "u": self.updated_ms,
        }

    @staticmethod
    def from_compact(data: Dict[str, Any]) -> "ClusterSnapshot":
        return ClusterSnapshot(
            name=data["n"],
            cluster_type=data.get("t", "unknown"),
            resources_by_type=data.get("r", {}),
            kubestellar_resources=data.get("k", []),
            updated_ms=data.get("u", int(time.time() * 1000)),
        )


class ContextSerializer:
    """Compact JSON serialization with content hashing."""

    @staticmethod
    def dumps(context: Dict[str, Any]) -> str:
        payload = {
            "v": 1,
            "ctx": context,
        }
        text = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return text

    @staticmethod
    def loads(text: str) -> Dict[str, Any]:
        data = json.loads(text)
        return data.get("ctx", {})

    @staticmethod
    def hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SharedContext:
    """Holds latest multi-cluster state and computes deltas."""

    def __init__(self) -> None:
        self._clusters: Dict[str, ClusterSnapshot] = {}
        self._last_hash: Optional[str] = None

    def update_cluster(self, snapshot: ClusterSnapshot) -> None:
        self._clusters[snapshot.name] = snapshot

    def to_model_context(self) -> Dict[str, Any]:
        # Compact schema suitable for LLM/system prompt inclusion
        return {
            "clusters": {name: snap.to_compact() for name, snap in self._clusters.items()}
        }

    def serialize(self) -> str:
        return ContextSerializer.dumps(self.to_model_context())

    def get_delta_if_changed(self) -> Optional[Dict[str, Any]]:
        text = self.serialize()
        h = ContextSerializer.hash(text)
        if h == self._last_hash:
            return None
        self._last_hash = h
        return {"hash": h, "context": json.loads(text)}


