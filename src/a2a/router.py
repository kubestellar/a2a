"""Inter-AI message routing utilities.

Provides helpers to route messages to topics based on KubeStellar context
properties and to address agents by capability.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def topic_for_cluster(cluster_name: str) -> str:
    return f"cluster.{cluster_name}"


def topic_for_resource(kind: str) -> str:
    return f"resource.{kind.lower()}"


def topic_for_role(role: str) -> str:
    return f"role.{role.lower()}"


def route_for_task(task: Dict[str, Any]) -> str:
    if "cluster" in task:
        return topic_for_cluster(task["cluster"])
    if "resource_kind" in task:
        return topic_for_resource(task["resource_kind"])
    return topic_for_role(task.get("role", "general"))


