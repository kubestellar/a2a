"""Gemini LLM Provider implementation."""

import json
from typing import Any, AsyncIterator, Dict, List, Optional, Union

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    genai = None
    HAS_GEMINI = False

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


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider."""

    MODELS = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-1.0-pro",
    ]

    def __init__(self, config: ProviderConfig):
        """Initialize Gemini provider."""
        if not HAS_GEMINI:
            raise ImportError(
                "google-generativeai package not installed. Install with: pip install google-generativeai"
            )

        super().__init__(config)

        # Set default model if not specified
        if config.model == "default":
            config.model = "gemini-2.0-flash"

        # Configure API key
        genai.configure(api_key=config.api_key)

        # Initialize Gemini model
        self.model = genai.GenerativeModel(config.model)

    def _convert_messages(self, messages: List[LLMMessage]) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Convert messages to Gemini format.
        
        Returns:
            Tuple of (gemini_messages, system_instruction)
        """
        gemini_messages = []
        system_instruction = None

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # Gemini doesn't support system role in messages, use system instruction instead
                if system_instruction is None:
                    system_instruction = msg.content
                else:
                    # Multiple system messages - combine them
                    system_instruction += f"\n\n{msg.content}"
            elif msg.role == MessageRole.USER:
                gemini_messages.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role == MessageRole.ASSISTANT:
                message = {"role": "model", "parts": [{"text": msg.content}]}
                if msg.tool_calls:
                    # Convert tool calls to Gemini format
                    for tc in msg.tool_calls:
                        message["parts"].append({
                            "function_call": {
                                "name": tc.name,
                                "args": tc.arguments
                            }
                        })
                gemini_messages.append(message)
            elif msg.role == MessageRole.TOOL:
                # Gemini doesn't support tool role, convert to user message with tool result format
                gemini_messages.append(
                    {"role": "user", "parts": [{"text": f"Tool result: {msg.content}"}]}
                )
            elif msg.role == MessageRole.THINKING:
                # Gemini does not have native thinking, append as annotation
                if gemini_messages and gemini_messages[-1]["role"] == "model":
                    gemini_messages[-1]["parts"].append({"text": f"<thinking>\n{msg.content}\n</thinking>"})

        return gemini_messages, system_instruction

    def _convert_tools_to_gemini(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools to Gemini format."""
        gemini_tools = []

        for tool in tools:
            # Clean schema for Gemini compatibility
            cleaned_schema = self._clean_schema_for_gemini(tool.get("inputSchema", {}))

            # Gemini expects tools in a specific format
            gemini_tool = {
                "function_declarations": [{
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": cleaned_schema,
                }]
            }
            gemini_tools.append(gemini_tool)

        return gemini_tools

    def _clean_schema_for_gemini(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Clean schema to be compatible with Gemini function calling."""
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
        # Keep only basic fields that Gemini supports
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
        """Parse tool calls from Gemini response."""
        tool_calls = []

        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate.content, "parts"):
                for part in candidate.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        try:
                            # Handle both string and dict arguments
                            if isinstance(part.function_call.args, str):
                                arguments = json.loads(part.function_call.args)
                            else:
                                arguments = part.function_call.args
                        except (json.JSONDecodeError, AttributeError):
                            arguments = {}

                        tool_calls.append(
                            ToolCall(
                                name=part.function_call.name,
                                arguments=arguments,
                                id=f"call_{len(tool_calls)}",  # Generate unique ID
                            )
                        )

        return tool_calls

    def _parse_usage(self, response) -> Optional[Dict[str, int]]:
        """Parse token usage from Gemini response."""
        if hasattr(response, "usage_metadata"):
            return {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count,
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
        """Generate response from Gemini."""
        gemini_messages, system_instruction = self._convert_messages(messages)

        # Add tool results if present
        if tool_results:
            for result in tool_results:
                gemini_messages.append(
                    {
                        "role": "user",
                        "parts": [{"text": f"Tool result: {result.content}"}],
                    }
                )

        # Create model with system instruction if needed
        model = self.model
        if system_instruction:
            model = genai.GenerativeModel(
                self.config.model,
                system_instruction=system_instruction
            )

        # Prepare generation config
        generation_config = {
            "temperature": self.config.temperature,
            "max_output_tokens": self.config.max_tokens or 1024,
        }

        # Convert tools if present
        gemini_tools = None
        if tools:
            gemini_tools = self._convert_tools_to_gemini(tools)

        if stream:
            return self._stream_response(gemini_messages, generation_config, gemini_tools, model, **kwargs)
        else:
            try:
                # Try with tools first
                if gemini_tools:
                    response = await model.generate_content_async(
                        gemini_messages,
                        generation_config=generation_config,
                        tools=gemini_tools,
                    )
                else:
                    response = await model.generate_content_async(
                        gemini_messages,
                        generation_config=generation_config,
                    )
            except Exception as e:
                # If tools fail, fall back to no tools
                if any(keyword in str(e).lower() for keyword in ["tools", "object", "system", "role", "function"]):
                    response = await model.generate_content_async(
                        gemini_messages,
                        generation_config=generation_config,
                    )
                else:
                    raise

            # Extract text response
            content = ""
            if response.candidates:
                content = response.candidates[0].content.parts[0].text

            # Parse thinking blocks
            content, thinking_blocks = self.parse_thinking_blocks(content)

            return LLMResponse(
                content=content,
                thinking_blocks=thinking_blocks,
                tool_calls=self._parse_tool_calls(response),
                usage=self._parse_usage(response),
                raw_response=response.to_dict() if hasattr(response, "to_dict") else None,
            )

    async def _stream_response(self, messages: List[Dict[str, Any]], generation_config: Dict[str, Any], tools: Optional[List[Dict[str, Any]]] = None, model = None, **kwargs) -> AsyncIterator[LLMResponse]:
        """Stream response from Gemini."""
        if model is None:
            model = self.model
            
        try:
            # Try with tools first
            if tools:
                stream = await model.generate_content_async(
                    messages,
                    stream=True,
                    generation_config=generation_config,
                    tools=tools,
                )
            else:
                stream = await model.generate_content_async(
                    messages,
                    stream=True,
                    generation_config=generation_config,
                )
        except Exception as e:
            # If tools fail, fall back to no tools
            if any(keyword in str(e).lower() for keyword in ["tools", "object", "system", "role", "function"]):
                stream = await model.generate_content_async(
                    messages,
                    stream=True,
                    generation_config=generation_config,
                )
            else:
                raise

        accumulated_content = ""
        async for chunk in stream:
            if chunk.candidates and chunk.candidates[0].content.parts:
                delta = chunk.candidates[0].content.parts[0].text
                accumulated_content += delta

                content, thinking_blocks = self.parse_thinking_blocks(accumulated_content)

                yield LLMResponse(
                    content=content,
                    thinking_blocks=thinking_blocks,
                    tool_calls=self._parse_tool_calls(chunk),
                    usage=self._parse_usage(chunk),
                )

    def supports_thinking(self) -> bool:
        return False

    def supports_tools(self) -> bool:
        return False  # Gemini tool support is experimental, disable for stability

    def get_model_list(self) -> List[str]:
        return self.MODELS


# Register provider
register_provider("gemini", GeminiProvider)
