"""OpenAI LLM Provider implementation."""

import json
from typing import Any, AsyncIterator, Dict, List, Optional, Union

try:
    from openai import AsyncOpenAI

    HAS_OPENAI = True
except ImportError:
    AsyncOpenAI = None
    HAS_OPENAI = False

from .base import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    MessageRole,
    ProviderConfig,
    ToolCall,
    ToolResult,
)
from .registry import register_provider


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider."""

    MODELS = [
        "gpt-4",
        "gpt-4-turbo",
        "gpt-4-turbo-preview",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-3.5-turbo",
    ]

    def __init__(self, config: ProviderConfig):
        """Initialize OpenAI provider."""
        if not HAS_OPENAI:
            raise ImportError(
                "openai package not installed. " "Install with: pip install openai"
            )

        super().__init__(config)

        # Set default model if not specified
        if config.model == "default":
            config.model = "gpt-4o"

        # Initialize OpenAI client
        self.client = AsyncOpenAI(api_key=config.api_key)

    def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """Convert messages to OpenAI format."""
        openai_messages = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                openai_messages.append({"role": "system", "content": msg.content})
            elif msg.role == MessageRole.USER:
                openai_messages.append({"role": "user", "content": msg.content})
            elif msg.role == MessageRole.ASSISTANT:
                message = {"role": "assistant", "content": msg.content}
                if msg.tool_calls:
                    # Convert tool calls to OpenAI format
                    message["tool_calls"] = []
                    for tc in msg.tool_calls:
                        message["tool_calls"].append(
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments),
                                },
                            }
                        )
                openai_messages.append(message)
            elif msg.role == MessageRole.TOOL:
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                )
            elif msg.role == MessageRole.THINKING:
                # Include thinking as part of assistant message
                if openai_messages and openai_messages[-1]["role"] == "assistant":
                    openai_messages[-1][
                        "content"
                    ] += f"\n\n<thinking>\n{msg.content}\n</thinking>"

        return openai_messages

    def _convert_tools_to_openai(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert tools to OpenAI format."""
        openai_tools = []

        for tool in tools:
            # Clean schema for OpenAI compatibility
            cleaned_schema = self._clean_schema_for_openai(tool.get("inputSchema", {}))

            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": cleaned_schema,
                },
            }
            openai_tools.append(openai_tool)

        return openai_tools

    def _clean_schema_for_openai(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Clean schema to be compatible with OpenAI function calling."""
        if not isinstance(schema, dict):
            return {}

        cleaned = {}

        # Only keep supported top-level fields
        supported_fields = {"type", "properties", "required", "description"}

        for key, value in schema.items():
            if key in supported_fields:
                if key == "properties" and isinstance(value, dict):
                    # Recursively clean properties
                    cleaned_properties = {}
                    for prop_name, prop_def in value.items():
                        cleaned_properties[prop_name] = self._clean_property_schema(
                            prop_def
                        )
                    cleaned[key] = cleaned_properties
                else:
                    cleaned[key] = value

        # Ensure we have type: object at the top level
        if "type" not in cleaned:
            cleaned["type"] = "object"

        return cleaned

    def _clean_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Clean individual property schema."""
        if not isinstance(prop_schema, dict):
            return prop_schema

        cleaned = {}
        # Keep only basic fields that OpenAI supports
        supported_fields = {"type", "description", "items", "properties", "enum"}

        for key, value in prop_schema.items():
            if key in supported_fields:
                if key == "items" and isinstance(value, dict):
                    # Clean array items schema
                    cleaned[key] = self._clean_property_schema(value)
                elif key == "properties" and isinstance(value, dict):
                    # Clean nested properties
                    cleaned[key] = {
                        k: self._clean_property_schema(v) for k, v in value.items()
                    }
                else:
                    cleaned[key] = value

        return cleaned

    def _parse_tool_calls(self, response) -> List[ToolCall]:
        """Parse tool calls from OpenAI response."""
        tool_calls = []

        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    tool_calls.append(
                        ToolCall(
                            name=tc.function.name,
                            arguments=arguments,
                            id=tc.id,
                        )
                    )

        return tool_calls

    def _parse_usage(self, response) -> Optional[Dict[str, int]]:
        """Parse token usage from response."""
        if hasattr(response, "usage") and response.usage:
            return {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        return None

    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_results: Optional[List[ToolResult]] = None,
        stream: bool = False,
        **kwargs,
    ) -> Union[LLMResponse, AsyncIterator[LLMResponse]]:
        """Generate response from OpenAI."""
        # Convert messages to OpenAI format
        openai_messages = self._convert_messages(messages)

        # Add tool results if any (for backward compatibility)
        if tool_results:
            for result in tool_results:
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.call_id,
                        "content": result.content,
                    }
                )

        # Prepare request parameters
        request_params = {
            "model": self.config.model,
            "messages": openai_messages,
            "temperature": self.config.temperature,
            "stream": stream,
        }

        if self.config.max_tokens:
            request_params["max_tokens"] = self.config.max_tokens

        if tools:
            request_params["tools"] = self._convert_tools_to_openai(tools)
            request_params["tool_choice"] = "auto"

        # Generate response
        if stream:
            return self._stream_response(**request_params)
        else:
            response = await self.client.chat.completions.create(**request_params)

            # Parse response
            content = ""
            if response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content

            # Parse thinking blocks (OpenAI doesn't have native thinking support)
            content, thinking_blocks = self.parse_thinking_blocks(content)

            return LLMResponse(
                content=content,
                thinking_blocks=thinking_blocks,
                tool_calls=self._parse_tool_calls(response),
                usage=self._parse_usage(response),
                raw_response=(
                    response.model_dump() if hasattr(response, "model_dump") else None
                ),
            )

    async def _stream_response(self, **request_params) -> AsyncIterator[LLMResponse]:
        """Stream response from OpenAI."""
        stream = await self.client.chat.completions.create(**request_params)

        accumulated_content = ""

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content_delta = chunk.choices[0].delta.content
                accumulated_content += content_delta

                # Parse thinking blocks from accumulated content
                content, thinking_blocks = self.parse_thinking_blocks(
                    accumulated_content
                )

                yield LLMResponse(
                    content=content,
                    thinking_blocks=thinking_blocks,
                    tool_calls=[],  # Tool calls come at the end
                    usage=self._parse_usage(chunk),
                )

    def supports_thinking(self) -> bool:
        """Check if provider supports thinking blocks."""
        return False  # OpenAI doesn't have native thinking support

    def supports_tools(self) -> bool:
        """Check if provider supports tool calling."""
        return True

    def get_model_list(self) -> List[str]:
        """Get list of available models."""
        return self.MODELS


# Register provider
register_provider("openai", OpenAIProvider)
