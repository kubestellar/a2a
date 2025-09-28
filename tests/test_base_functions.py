"""Tests for base functions and registry."""

from typing import Any, Dict

import pytest

from src.shared.base_functions import BaseFunction, FunctionRegistry, async_to_sync


class MockFunction(BaseFunction):
    """Mock function for testing."""

    def __init__(self):
        super().__init__(
            name="mock_function", description="A mock function for testing"
        )

    async def execute(self, param1: str = "default") -> Dict[str, Any]:
        """Execute mock function."""
        return {"result": f"Mocked: {param1}"}

    def get_schema(self) -> Dict[str, Any]:
        """Get mock schema."""
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "Test parameter",
                    "default": "default",
                }
            },
            "required": [],
        }


class SyncMockFunction(BaseFunction):
    """Synchronous mock function for testing."""

    def __init__(self):
        super().__init__(
            name="sync_mock_function", description="A synchronous mock function"
        )

    def execute(self, value: int = 42) -> Dict[str, Any]:
        """Execute sync function."""
        return {"value": value * 2}

    def get_schema(self) -> Dict[str, Any]:
        """Get schema."""
        return {
            "type": "object",
            "properties": {"value": {"type": "integer", "default": 42}},
            "required": [],
        }


def test_base_function_initialization():
    """Test BaseFunction initialization."""
    func = MockFunction()
    assert func.name == "mock_function"
    assert func.description == "A mock function for testing"


@pytest.mark.asyncio
async def test_mock_function_execution():
    """Test mock function execution."""
    func = MockFunction()
    result = await func.execute(param1="test")
    assert result == {"result": "Mocked: test"}

    # Test with default
    result = await func.execute()
    assert result == {"result": "Mocked: default"}


def test_mock_function_schema():
    """Test mock function schema."""
    func = MockFunction()
    schema = func.get_schema()
    assert schema["type"] == "object"
    assert "param1" in schema["properties"]
    assert schema["properties"]["param1"]["type"] == "string"


def test_function_registry():
    """Test FunctionRegistry."""
    registry = FunctionRegistry()

    # Test empty registry
    assert registry.list_all() == []
    assert registry.get("nonexistent") is None

    # Register function
    func = MockFunction()
    registry.register(func)

    # Test retrieval
    assert registry.get("mock_function") == func
    assert len(registry.list_all()) == 1
    assert registry.list_all()[0] == func

    # Test schemas
    schemas = registry.get_schemas()
    assert "mock_function" in schemas
    assert schemas["mock_function"] == func.get_schema()


def test_function_registry_multiple():
    """Test FunctionRegistry with multiple functions."""
    registry = FunctionRegistry()

    func1 = MockFunction()
    func2 = SyncMockFunction()

    registry.register(func1)
    registry.register(func2)

    assert len(registry.list_all()) == 2
    assert registry.get("mock_function") == func1
    assert registry.get("sync_mock_function") == func2

    schemas = registry.get_schemas()
    assert len(schemas) == 2
    assert "mock_function" in schemas
    assert "sync_mock_function" in schemas


def test_async_to_sync_decorator():
    """Test async_to_sync decorator."""

    async def async_function(x: int) -> int:
        return x * 2

    sync_function = async_to_sync(async_function)
    result = sync_function(5)
    assert result == 10


def test_async_to_sync_with_function():
    """Test async_to_sync with BaseFunction."""
    func = MockFunction()
    sync_execute = async_to_sync(func.execute)

    result = sync_execute(param1="sync_test")
    assert result == {"result": "Mocked: sync_test"}


def test_function_registry_overwrite():
    """Test that registering a function with the same name overwrites."""
    registry = FunctionRegistry()

    func1 = MockFunction()
    registry.register(func1)

    # Create another function with same name
    class AnotherMockFunction(MockFunction):
        async def execute(self, **kwargs) -> Dict[str, Any]:
            return {"result": "different"}

    func2 = AnotherMockFunction()
    registry.register(func2)

    # Should have overwritten
    assert len(registry.list_all()) == 1
    assert registry.get("mock_function") == func2

    # Verify it's the new function
    result = async_to_sync(registry.get("mock_function").execute)()
    assert result == {"result": "different"}
