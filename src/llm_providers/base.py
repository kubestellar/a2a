"""Base LLM Provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Union


class MessageRole(str, Enum):
    """Message roles in conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    THINKING = "thinking"  # For internal reasoning
    TOOL = "tool"  # For tool call results


@dataclass
class LLMMessage:
    """Single message in conversation."""

    role: MessageRole
    content: str
    metadata: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List["ToolCall"]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ThinkingBlock:
    """Represents a thinking/reasoning block."""

    content: str
    timestamp: Optional[float] = None


@dataclass
class ToolCall:
    """Represents a tool/function call."""

    name: str
    arguments: Dict[str, Any]
    id: Optional[str] = None


@dataclass
class ToolResult:
    """Result from a tool execution."""

    call_id: str
    content: str
    success: bool = True
    error: Optional[str] = None


@dataclass
class LLMResponse:
    """Response from LLM provider."""

    content: str
    thinking_blocks: Optional[List[ThinkingBlock]] = None
    tool_calls: Optional[List[ToolCall]] = None
    raw_response: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, int]] = None

    def __post_init__(self):
        if self.thinking_blocks is None:
            self.thinking_blocks = []
        if self.tool_calls is None:
            self.tool_calls = []


@dataclass
class ProviderConfig:
    """Configuration for LLM provider."""

    api_key: str
    model: str = "default"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    timeout: int = 60
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: ProviderConfig):
        """Initialize provider with configuration."""
        self.config = config
        self._validate_config()

    def _validate_config(self):
        """Validate provider configuration."""
        if not self.config.api_key:
            raise ValueError(f"{self.__class__.__name__} requires an API key")

    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_results: Optional[List[ToolResult]] = None,
        stream: bool = False,
        **kwargs,
    ) -> Union[LLMResponse, AsyncIterator[LLMResponse]]:
        """
        Generate response from LLM.

        Args:
            messages: Conversation history
            tools: Available tools/functions
            tool_results: Results from previous tool calls
            stream: Whether to stream the response
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse or async iterator of responses if streaming
        """
        pass

    @abstractmethod
    def supports_thinking(self) -> bool:
        """Check if provider supports thinking/reasoning blocks."""
        pass

    @abstractmethod
    def supports_tools(self) -> bool:
        """Check if provider supports tool/function calling."""
        pass

    @abstractmethod
    def get_model_list(self) -> List[str]:
        """Get list of available models for this provider."""
        pass

    def format_tool_for_provider(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Format tool definition for provider-specific format."""
        return tool

    def parse_thinking_blocks(self, response: str) -> tuple[str, List[ThinkingBlock]]:
        """
        Parse thinking blocks from response.

        Returns:
            Tuple of (content without thinking blocks, list of thinking blocks)
        """
        # Default implementation - providers can override
        import re

        thinking_pattern = r"<thinking>(.*?)</thinking>"
        thinking_blocks = []

        for match in re.finditer(thinking_pattern, response, re.DOTALL):
            thinking_blocks.append(ThinkingBlock(content=match.group(1).strip()))

        # Remove thinking blocks from content
        content = re.sub(thinking_pattern, "", response, flags=re.DOTALL).strip()

        return content, thinking_blocks
