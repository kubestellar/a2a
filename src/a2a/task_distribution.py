"""Task distribution algorithms for A2A coordination."""

from __future__ import annotations

from typing import Any, Dict, List


def round_robin(agents: List[str], tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not agents:
        return []
    assigned: List[Dict[str, Any]] = []
    for i, task in enumerate(tasks):
        agent = agents[i % len(agents)]
        assigned.append({**task, "assignee": agent})
    return assigned


def by_capacity(agents: List[Dict[str, Any]], tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # agents: [{id: str, capacity: int, load: int}]
    sorted_agents = sorted(agents, key=lambda a: (a.get("load", 0) / max(a.get("capacity", 1), 1)))
    assigned: List[Dict[str, Any]] = []
    idx = 0
    for task in tasks:
        agent = sorted_agents[idx % len(sorted_agents)]
        assigned.append({**task, "assignee": agent["id"]})
        agent["load"] = agent.get("load", 0) + 1
        sorted_agents = sorted(sorted_agents, key=lambda a: (a.get("load", 0) / max(a.get("capacity", 1), 1)))
    return assigned


