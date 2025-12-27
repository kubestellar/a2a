"""Base functions shared between MCP server and A2A agent."""

import asyncio
import functools
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional


class BaseFunction(ABC):
    """Base class for all functions."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute the function with given parameters."""
        pass

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Return JSON schema for function parameters."""

    def validate_inputs(self, inputs: Dict[str, Any]) -> None:
        """Validate incoming inputs against the declared schema.

        Rejects missing required fields or explicit ``None`` values unless the
        schema property declares ``nullable: True``.
        """

        schema = self.get_schema() or {}
        properties: Dict[str, Dict[str, Any]] = schema.get("properties", {}) or {}
        required_fields = set(schema.get("required", []))

        for field in required_fields:
            if field not in inputs or inputs[field] is None:
                raise ValueError(f"Parameter '{field}' is required and cannot be null")

        for field, value in inputs.items():
            if value is None:
                property_schema = properties.get(field)
                if property_schema is None:
                    continue
                if property_schema.get("nullable") is True:
                    continue
                raise ValueError(f"Parameter '{field}' cannot be null")
        pass


class CreatePlanFunction(BaseFunction):
    """A special function to create a plan of execution."""

    def __init__(self):
        super().__init__(
            "create_plan",
            "Creates a plan of steps to execute to fulfill the user's request. Use this when multiple steps are required.",
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """This function does not execute anything, it's a placeholder for the plan."""
        return {"status": "plan created", "steps": kwargs.get("steps", [])}

    def get_schema(self) -> Dict[str, Any]:
        """Return the schema for the create_plan function."""
        return {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "function_name": {"type": "string"},
                            "arguments": {"type": "object"},
                        },
                        "required": ["function_name", "arguments"],
                    },
                }
            },
            "required": ["steps"],
        }


class FunctionRegistry:
    """Registry to manage all available functions."""

    def __init__(self):
        self._functions: Dict[str, BaseFunction] = {}

    def register(self, function: BaseFunction) -> None:
        """Register a new function."""
        self._functions[function.name] = function

    def get(self, name: str) -> Optional[BaseFunction]:
        """Get a function by name."""
        return self._functions.get(name)

    def list_all(self) -> List[BaseFunction]:
        """List all registered functions."""
        return list(self._functions.values())

    def get_schemas(self) -> Dict[str, Dict[str, Any]]:
        """Get schemas for all functions."""
        return {name: func.get_schema() for name, func in self._functions.items()}


def async_to_sync(func: Callable) -> Callable:
    """Convert async function to sync for CLI usage."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(*args, **kwargs))

    return wrapper


# Global registry instance
function_registry = FunctionRegistry()

# Register the create_plan function
function_registry.register(CreatePlanFunction())
