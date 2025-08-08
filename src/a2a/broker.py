"""In-process A2A message broker with topics and direct delivery.

This is a minimal async broker abstraction to enable testing and local
coordination. It can be replaced by a distributed backend later (NATS, Redis,
Kafka). The interface is intentionally small for portability.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncIterator, Dict, Optional, Set

from .protocol import Message


class A2ABroker:
    """Simple async broker supporting pub/sub and direct send."""

    def __init__(self) -> None:
        self._topic_queues: Dict[str, Set[asyncio.Queue[Message]]] = defaultdict(set)
        self._direct_queues: Dict[str, asyncio.Queue[Message]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str) -> AsyncIterator[Message]:
        queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=1024)
        async with self._lock:
            self._topic_queues[topic].add(queue)

        try:
            while True:
                msg = await queue.get()
                yield msg
        finally:
            async with self._lock:
                self._topic_queues[topic].discard(queue)

    async def register_direct_inbox(self, agent_id: str) -> asyncio.Queue[Message]:
        async with self._lock:
            if agent_id not in self._direct_queues:
                self._direct_queues[agent_id] = asyncio.Queue(maxsize=1024)
            return self._direct_queues[agent_id]

    async def publish(self, message: Message) -> None:
        if message.topic is None:
            return
        async with self._lock:
            for queue in list(self._topic_queues.get(message.topic, [])):
                # best effort, drop on full to keep latency low
                if not queue.full():
                    queue.put_nowait(message)

    async def send(self, message: Message) -> bool:
        if message.target_id is None:
            return False
        async with self._lock:
            inbox = self._direct_queues.get(message.target_id)
            if inbox is None:
                return False
            if inbox.full():
                return False
            inbox.put_nowait(message)
            return True


