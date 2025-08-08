"""Google Gemini LLM Provider implementation."""

import json
from typing import Any, AsyncIterator, Dict, List, Optional, Union

try:
    import google.generativeai as genai
    from google.generativeai.types import GenerateContentResponse

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
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-1.0-pro",
        "gemini-1.0-pro-vision",
    ]

    def __init__(self, config: ProviderConfig):
        """Initialize Gemini provider."""
        if not HAS_GEMINI:
            raise ImportError(
                "google-generativeai package not installed. "
                "Install with: pip install google-generativeai"
            )

        super().__init__(config)

        # Set default model if not specified
        if config.model == "default":
            config.model = "gemini-1.5-flash"

        # Configure Gemini
        genai.configure(api_key=config.api_key)
        self.model = genai.GenerativeModel(config.model)

    def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """Convert messages to Gemini format."""
        gemini_messages = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # Gemini doesn't have system messages, so we'll prepend to the first user message
                continue
            elif msg.role == MessageRole.USER:
                gemini_messages.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role == MessageRole.ASSISTANT:
                content = msg.content
                if msg.tool_calls:
                    # Add tool calls to content
                    tool_calls_text = []
                    for tc in msg.tool_calls:
                        tool_calls_text.append(
                            f"<tool_call>\n<name>{tc.name}</name>\n<arguments>{json.dumps(tc.arguments)}</arguments>\n</tool_call>"
                        )
                    content += "\n" + "\n".join(tool_calls_text)
                
                gemini_messages.append({"role": "model", "parts": [{"text": content}]})
            elif msg.role == MessageRole.TOOL:
                # Add tool results as user message
                gemini_messages.append(
                    {
                        "role": "user",
                        "parts": [{"text": f"<tool_result>\n{msg.content}\n</tool_result>"}],
                    }
                )
            elif msg.role == MessageRole.THINKING:
                # Include thinking as part of model message
                if gemini_messages and gemini_messages[-1]["role"] == "model":
                    gemini_messages[-1]["parts"][0]["text"] += f"\n\n<thinking>\n{msg.content}\n</thinking>"

        return gemini_messages

    def _convert_tools_to_gemini(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert tools to Gemini format."""
        gemini_tools = []
        
        for tool in tools:
            gemini_tool = {
                "function_declarations": [
                    {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": self._clean_schema_for_gemini(tool["inputSchema"]),
                    }
                ]
            }
            gemini_tools.append(gemini_tool)
        
        return gemini_tools

    def _clean_schema_for_gemini(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and convert schema for Gemini format."""
        if not schema:
            return {"type": "object", "properties": {}}

        # Gemini uses a different schema format
        gemini_schema = {
            "type": schema.get("type", "object"),
        }

        if "properties" in schema:
            gemini_schema["properties"] = {}
            for prop_name, prop_schema in schema["properties"].items():
                gemini_schema["properties"][prop_name] = self._clean_property_schema(prop_schema)

        if "required" in schema:
            gemini_schema["required"] = schema["required"]

        return gemini_schema

    def _clean_property_schema(self, prop_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Clean individual property schema for Gemini."""
        cleaned = {
            "type": prop_schema.get("type", "string"),
        }

        if "description" in prop_schema:
            cleaned["description"] = prop_schema["description"]

        if "enum" in prop_schema:
            cleaned["enum"] = prop_schema["enum"]

        if prop_schema.get("type") == "array" and "items" in prop_schema:
            cleaned["items"] = self._clean_property_schema(prop_schema["items"])

        return cleaned

    def _parse_tool_calls(self, response_text: str) -> List[ToolCall]:
        """Parse tool calls from Gemini response."""
        import re

        tool_calls = []
        tool_call_pattern = r"<tool_call>\s*<name>([^<]+)</name>\s*<arguments>([^<]+)</arguments>\s*</tool_call>"
        
        for match in re.finditer(tool_call_pattern, response_text, re.DOTALL):
            name = match.group(1).strip()
            arguments_text = match.group(2).strip()
            
            try:
                arguments = json.loads(arguments_text)
            except json.JSONDecodeError:
                # Fallback: try to parse as simple key-value pairs
                arguments = {}
                for line in arguments_text.split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        arguments[key.strip()] = value.strip()
            
            tool_calls.append(ToolCall(
                name=name,
                arguments=arguments,
                id=f"call_{len(tool_calls)}"
            ))

        return tool_calls

    def _parse_usage(self, response: GenerateContentResponse) -> Optional[Dict[str, int]]:
        """Parse usage information from Gemini response."""
        if hasattr(response, 'usage_metadata'):
            usage = response.usage_metadata
            return {
                "prompt_tokens": getattr(usage, 'prompt_token_count', 0),
                "completion_tokens": getattr(usage, 'candidates_token_count', 0),
                "total_tokens": getattr(usage, 'total_token_count', 0),
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
        """
        Generate response from Gemini.

        Args:
            messages: Conversation history
            tools: Available tools/functions
            tool_results: Results from previous tool calls
            stream: Whether to stream the response
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse or async iterator of responses if streaming
        """
        if stream:
            return self._stream_response(messages, tools, tool_results, **kwargs)

        # Convert messages to Gemini format
        gemini_messages = self._convert_messages(messages)
        
        # Convert tools if provided
        gemini_tools = None
        if tools:
            gemini_tools = self._convert_tools_to_gemini(tools)

        # Prepare generation config
        generation_config = {
            "temperature": self.config.temperature,
        }
        if self.config.max_tokens:
            generation_config["max_output_tokens"] = self.config.max_tokens

        # Add any extra parameters
        generation_config.update(self.config.extra_params or {})
        generation_config.update(kwargs)

        try:
            # Create chat session
            chat = self.model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
            
            # Generate response
            response = await chat.send_message_async(
                gemini_messages[-1]["parts"][0]["text"] if gemini_messages else "",
                generation_config=generation_config,
                tools=gemini_tools,
            )

            # Extract content
            content = response.text if response.text else ""
            
            # Parse tool calls
            tool_calls = self._parse_tool_calls(content)
            
            # Remove tool calls from content
            import re
            content = re.sub(r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL).strip()
            
            # Parse thinking blocks
            content, thinking_blocks = self.parse_thinking_blocks(content)
            
            # Parse usage
            usage = self._parse_usage(response)

            return LLMResponse(
                content=content,
                thinking_blocks=thinking_blocks,
                tool_calls=tool_calls,
                raw_response=response,
                usage=usage,
            )

        except Exception as e:
            raise Exception(f"Gemini API error: {e}")

    async def _stream_response(
        self, messages: List[LLMMessage], tools: Optional[List[Dict[str, Any]]] = None, 
        tool_results: Optional[List[ToolResult]] = None, **kwargs
    ) -> AsyncIterator[LLMResponse]:
        """Stream response from Gemini."""
        # For now, we'll return a single response since streaming with tools is complex
        response = await self.generate(messages, tools, tool_results, stream=False, **kwargs)
        yield response

    def supports_thinking(self) -> bool:
        """Check if provider supports thinking/reasoning blocks."""
        return True

    def supports_tools(self) -> bool:
        """Check if provider supports tool/function calling."""
        return True

    def get_model_list(self) -> List[str]:
        """Get list of available models for this provider."""
        return self.MODELS


# Register the provider
register_provider("gemini", GeminiProvider)
