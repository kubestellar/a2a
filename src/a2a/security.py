"""Simple authentication and authorization helpers for A2A.

This module provides HMAC-based token validation and role-based checks. It is
kept minimal for local development and can be replaced by a more robust layer.
"""

from __future__ import annotations

import hmac
import os
from hashlib import sha256
from typing import Optional

from ..llm_providers.config import get_config_manager


class AuthManager:
    def __init__(self, secret: Optional[str] = None) -> None:
        config = get_config_manager()
        resolved_secret = secret or config.get_a2a_secret()
        if not resolved_secret:
            raise ValueError(
                "A2A secret is not configured. Use 'kubestellar config a2a set-secret <VALUE>' or set A2A_SECRET."
            )
        self._secret = resolved_secret.encode("utf-8")
        self._config = config

    def issue_token(self, agent_id: str) -> str:
        digest = hmac.new(self._secret, agent_id.encode("utf-8"), sha256).hexdigest()
        return digest

    def verify(self, agent_id: str, token: str) -> bool:
        expected = self.issue_token(agent_id)
        return hmac.compare_digest(expected, token)

    def set_role(self, agent_id: str, role: str) -> None:
        self._config.set_agent_role(agent_id, role)

    def has_role(self, agent_id: str, required_role: str) -> bool:
        return self._config.get_agent_role(agent_id) == required_role


