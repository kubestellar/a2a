"""MCP Server implementation."""

import asyncio
import json
import logging
from typing import Any, Dict

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from src.shared.base_functions import function_registry
from src.shared.functions import initialize_functions
from src.shared.task_queue import TaskPriority, task_executor

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle_call_tool(
    name: str, arguments: Dict[str, Any] | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests from MCP clients."""
    function = function_registry.get(name)
    if not function:
        raise ValueError(f"Unknown function: {name}")

    try:
        result = await task_executor.run_function(
            function,
            arguments or {},
            priority=TaskPriority.MEDIUM,
        )
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        logger.error(f"Error executing function {name}: {e}")
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_list_tools() -> list[types.Tool]:
    """List all available tools for MCP clients."""
    tools = []
    for function in function_registry.list_all():
        schema = function.get_schema()
        tools.append(
            types.Tool(
                name=function.name, description=function.description, inputSchema=schema
            )
        )
    return tools


async def run_server():
    """Run the MCP server."""
    # Initialize functions
    initialize_functions()

    server = Server("kubestellar-mcp-server")

    # Register handlers
    server.set_request_handler(types.ListToolsRequest, handle_list_tools)
    server.set_request_handler(types.CallToolRequest, handle_call_tool)

    # Run the server
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="kubestellar-mcp-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main():
    """Main entry point for MCP server."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
