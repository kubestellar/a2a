"""Tests for priority task executor."""

import asyncio
from typing import Any

import pytest

from src.shared.base_functions import BaseFunction
from src.shared.task_queue import PriorityTaskExecutor, TaskPriority


class _AsyncFunction(BaseFunction):
    """Async function that records execution order."""

    def __init__(self, name: str, recorder: list[str]):
        super().__init__(name=name, description="recording function")
        self._recorder = recorder

    async def execute(self, **kwargs: Any):  # type: ignore[override]
        """Record execution and return identifying marker."""
        await asyncio.sleep(0)  # yield control
        self._recorder.append(self.name)
        return {"name": self.name}

    def get_schema(self):  # type: ignore[override]
        return {"type": "object", "properties": {}}


@pytest.mark.asyncio
async def test_priority_executor_orders_tasks():
    """High priority tasks should run before medium and low."""

    executor = PriorityTaskExecutor()
    executed: list[str] = []

    high = _AsyncFunction("high", executed)
    med = _AsyncFunction("medium", executed)
    low = _AsyncFunction("low", executed)

    await asyncio.gather(
        executor.run_function(low, priority=TaskPriority.LOW),
        executor.run_function(high, priority=TaskPriority.HIGH),
        executor.run_function(med, priority=TaskPriority.MEDIUM),
    )
    assert executed == ["high", "medium", "low"]

    await executor.shutdown()


def test_priority_from_string_defaults():
    """String parsing should handle casing and default to medium."""

    assert TaskPriority.from_string(None) is TaskPriority.MEDIUM
    assert TaskPriority.from_string("HIGH") is TaskPriority.HIGH
    assert TaskPriority.from_string("medium") is TaskPriority.MEDIUM
    assert TaskPriority.from_string("Low") is TaskPriority.LOW
