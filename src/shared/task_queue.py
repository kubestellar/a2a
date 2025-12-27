"""Priority-based task execution utilities for A2A."""

from __future__ import annotations

import asyncio
import contextlib
import heapq
import itertools
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

from src.shared.base_functions import BaseFunction


class TaskPriority(str, Enum):
    """Supported execution priority levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @classmethod
    def from_string(cls, value: Optional[str]) -> "TaskPriority":
        """Parse a string into a priority, defaulting to medium."""

        if not value:
            return cls.MEDIUM
        try:
            return cls(value.lower())
        except ValueError as exc:  # pragma: no cover - click guards values
            raise ValueError(f"Unknown priority '{value}'") from exc


_PRIORITY_ORDER = {
    TaskPriority.HIGH: 0,
    TaskPriority.MEDIUM: 1,
    TaskPriority.LOW: 2,
}


@dataclass
class _QueuedTask:
    """Internal representation of queued work."""

    create_coro: Callable[[], Awaitable[Any]]
    future: asyncio.Future


class PriorityTaskExecutor:
    """Execute functions according to a priority-aware queue."""

    def __init__(self) -> None:
        self._queue: list[tuple[int, int, _QueuedTask]] = []
        self._counter = itertools.count()
        self._worker: Optional[asyncio.Task[Any]] = None
        self._lock = asyncio.Lock()

    async def _ensure_worker(self) -> None:
        """Start a worker if one is not already running."""

        if self._worker and not self._worker.done():
            return

        loop = asyncio.get_running_loop()
        self._worker = loop.create_task(self._worker_loop())

    async def _worker_loop(self) -> None:
        """Continuously drain the heap until no tasks remain."""

        while True:
            async with self._lock:
                if not self._queue:
                    self._worker = None
                    return
                priority, order, task = heapq.heappop(self._queue)

            if task.future.cancelled():
                continue

            try:
                result = await task.create_coro()
            except Exception as exc:  # pragma: no cover - defensive
                if not task.future.cancelled():
                    task.future.set_exception(exc)
            else:
                if not task.future.cancelled():
                    task.future.set_result(result)

    async def submit(
        self,
        create_coro: Callable[[], Awaitable[Any]],
        *,
        priority: TaskPriority = TaskPriority.MEDIUM,
    ) -> Any:
        """Queue a coroutine factory and await its result."""

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()

        queued = _QueuedTask(create_coro=create_coro, future=future)
        async with self._lock:
            heapq.heappush(
                self._queue,
                (_PRIORITY_ORDER[priority], next(self._counter), queued),
            )
            await self._ensure_worker()

        try:
            return await future
        except asyncio.CancelledError:
            # Ensure cancellation propagates to worker loop.
            future.cancel()
            raise

    async def run_function(
        self,
        function: BaseFunction,
        params: Optional[Dict[str, Any]] = None,
        *,
        priority: TaskPriority = TaskPriority.MEDIUM,
    ) -> Any:
        """Execute a BaseFunction via the priority queue."""

        params = params or {}

        async def _invoke() -> Any:
            result = function.execute(**params)
            if asyncio.iscoroutine(result):
                return await result
            return result

        return await self.submit(_invoke, priority=priority)

    async def shutdown(self) -> None:
        """Cancel outstanding work for clean test teardown."""

        async with self._lock:
            while self._queue:
                _, _, task = heapq.heappop(self._queue)
                if not task.future.done():
                    task.future.cancel()
            worker = self._worker
            self._worker = None

        if worker:
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker


# Shared executor instance for CLI, agent, and MCP server.
task_executor = PriorityTaskExecutor()

