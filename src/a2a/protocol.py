"""A2A protocol primitives for agent-to-agent messaging.

Defines message types, envelopes, and helpers for serialization.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class MessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    HEARTBEAT = "heartbeat"
    REGISTER = "register"
    PROPOSAL = "proposal"
    VOTE = "vote"
    TASK = "task"


@dataclass
class Message:
    """Protocol message envelope.

    All messages are routed through a broker by topic or direct target.
    """

    type: MessageType
    sender_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: Optional[str] = None
    target_id: Optional[str] = None
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    trace_id: Optional[str] = None
    auth_token: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "sender_id": self.sender_id,
            "payload": self.payload,
            "topic": self.topic,
            "target_id": self.target_id,
            "timestamp_ms": self.timestamp_ms,
            "trace_id": self.trace_id,
            "auth_token": self.auth_token,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Message":
        return Message(
            id=data.get("id") or str(uuid.uuid4()),
            type=MessageType(data["type"]),
            sender_id=data["sender_id"],
            payload=data.get("payload", {}),
            topic=data.get("topic"),
            target_id=data.get("target_id"),
            timestamp_ms=data.get("timestamp_ms", int(time.time() * 1000)),
            trace_id=data.get("trace_id"),
            auth_token=data.get("auth_token"),
        )


@dataclass
class AgentInfo:
    """Registered agent metadata."""

    agent_id: str
    capabilities: Dict[str, Any] = field(default_factory=dict)
    last_heartbeat_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    auth_token_hash: Optional[str] = None


