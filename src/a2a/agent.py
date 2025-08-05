"""Interactive agent mode for a2a CLI."""

import asyncio
import json
import sys
from typing import Any, Dict, List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from ..llm_providers import (
    BaseLLMProvider,
    LLMMessage,
    MessageRole,
    ProviderConfig,
    get_provider,
)
from ..llm_providers.config import get_config_manager
from ..shared.base_functions import function_registry
from ..shared.functions import initialize_functions


class AgentChat:
    """Interactive agent chat interface."""

    def __init__(self, provider_name: Optional[str] = None):
        """Initialize agent chat."""
        self.console = Console()
        self.config_manager = get_config_manager()
        self.messages: List[LLMMessage] = []
        self.provider: Optional[BaseLLMProvider] = None
        self.session = PromptSession(
            history=FileHistory(str(self.config_manager.config_dir / "chat_history"))
        )

        # Initialize functions
        initialize_functions()

        # Set up provider
        self._setup_provider(provider_name)

        # UI settings
        self.ui_config = self.config_manager.load_config().get("ui", {})
        self.show_thinking = self.ui_config.get("show_thinking", True)
        self.show_token_usage = self.ui_config.get("show_token_usage", True)

        # Style for prompt
        self.prompt_style = Style.from_dict(
            {
                "prompt": "#00aa00 bold",
                "provider": "#888888",
            }
        )

    def _setup_provider(self, provider_name: Optional[str] = None):
        """Set up LLM provider."""
        # Determine provider
        if provider_name is None:
            provider_name = self.config_manager.get_default_provider()
            if provider_name is None:
                provider_name = "openai"  # Default fallback

        # Get API key
        api_key = self.config_manager.get_api_key(provider_name)
        if not api_key:
            self.console.print(
                f"[red]No API key found for {provider_name}.[/red]\n"
                f"Please set it with: kubestellar config set-key {provider_name} YOUR_API_KEY"
            )
            sys.exit(1)

        # Load provider config
        config = self.config_manager.load_config()
        provider_config = config.get("providers", {}).get(provider_name, {})

        # Create provider
        try:
            self.provider = get_provider(
                provider_name,
                ProviderConfig(
                    api_key=api_key,
                    model=provider_config.get("model", "default"),
                    temperature=provider_config.get("temperature", 0.7),
                    max_tokens=provider_config.get("max_tokens"),
                ),
            )
            self.provider_name = provider_name
        except Exception as e:
            self.console.print(f"[red]Failed to initialize {provider_name}: {e}[/red]")
            sys.exit(1)

    def _format_prompt(self) -> List[tuple]:
        """Format the input prompt."""
        return FormattedText(
            [
                ("class:provider", f"[{self.provider_name}] "),
                ("class:prompt", "▶ "),
            ]
        )

    async def _execute_function(self, function_name: str, args: Dict[str, Any]) -> str:
        """Execute a KubeStellar function."""
        function = function_registry.get(function_name)
        if not function:
            return f"Error: Unknown function '{function_name}'"

        try:
            result = await function.execute(**args)
            return json.dumps(result, indent=2)
        except Exception as e:
            return f"Error executing {function_name}: {str(e)}"

    def _prepare_tools(self) -> List[Dict[str, Any]]:
        """Prepare available tools for the LLM."""
        tools = []
        for function in function_registry.list_all():
            schema = function.get_schema()
            tools.append(
                {
                    "name": function.name,
                    "description": function.description,
                    "inputSchema": schema,
                }
            )
        return tools

    def _display_thinking(self, thinking_blocks):
        """Display thinking blocks if enabled."""
        if not self.show_thinking or not thinking_blocks:
            return

        for i, block in enumerate(thinking_blocks):
            if block and hasattr(block, "content"):
                # Show thinking with Claude Code-like styling
                thinking_title = f"[dim]💭 Thinking{f' {i+1}' if len(thinking_blocks) > 1 else ''}[/dim]"
                self.console.print(
                    Panel(
                        block.content.strip(),
                        title=thinking_title,
                        border_style="bright_black",
                        padding=(1, 2),
                        expand=False,
                        title_align="left",
                    )
                )
                # Add a small gap between thinking blocks
                if i < len(thinking_blocks) - 1:
                    self.console.print()

    def _display_token_usage(self, usage: Optional[Dict[str, int]]):
        """Display token usage if enabled."""
        if not self.show_token_usage or not usage:
            return

        # Create a more Claude Code-like token display
        usage_parts = []
        if "prompt_tokens" in usage:
            usage_parts.append(
                f"[dim]Prompt tokens:[/dim] [cyan]{usage['prompt_tokens']}[/cyan]"
            )
        if "completion_tokens" in usage:
            usage_parts.append(
                f"[dim]Completion tokens:[/dim] [cyan]{usage['completion_tokens']}[/cyan]"
            )
        if "total_tokens" in usage:
            usage_parts.append(
                f"[dim]Total tokens:[/dim] [cyan]{usage['total_tokens']}[/cyan]"
            )

        if usage_parts:
            usage_text = " • ".join(usage_parts)
            self.console.print(f"\n[bright_black]💳 {usage_text}[/bright_black]")

    async def _handle_message(self, user_input: str):
        """Handle a user message."""
        # Add user message
        self.messages.append(LLMMessage(role=MessageRole.USER, content=user_input))

        # Add visual feedback for processing
        self.console.print()

        # Prepare system message with available functions
        system_message = self._prepare_system_message()

        # Create conversation with system message
        conversation = [
            LLMMessage(role=MessageRole.SYSTEM, content=system_message),
            *self.messages,
        ]

        # Get available tools
        tools = self._prepare_tools()

        # Generate response
        try:
            # Show processing indicator
            with self.console.status("[dim]🤔 Thinking...[/dim]", spinner="dots"):
                response = await self.provider.generate(
                    messages=conversation,
                    tools=tools,  # Re-enable tool calling
                    stream=False,  # TODO: Add streaming support
                )

            # Display thinking blocks
            self._display_thinking(response.thinking_blocks)

            # Handle tool calls
            if response.tool_calls:
                tool_results = []
                for tool_call in response.tool_calls:
                    if tool_call.name:  # Only execute if function name is not empty
                        # Show function execution with spinner
                        with self.console.status(
                            f"[dim]⚙️  Executing: {tool_call.name}[/dim]", spinner="dots"
                        ):
                            result = await self._execute_function(
                                tool_call.name, tool_call.arguments
                            )
                        tool_results.append(
                            {"call_id": tool_call.id, "content": result}
                        )

                        # Display completion
                        self.console.print(
                            f"[green]✓[/green] [dim]Completed: {tool_call.name}[/dim]"
                        )

                # If we have tool results, we need to get AI's response to process the data
                if tool_results:
                    self.console.print("[dim]📊 Processing data...[/dim]")

                    # Add the assistant's tool call message to conversation
                    self.messages.append(
                        LLMMessage(
                            role=MessageRole.ASSISTANT,
                            content=response.content or "",
                            tool_calls=response.tool_calls,
                        )
                    )

                    # Add tool result messages
                    for tr in tool_results:
                        self.messages.append(
                            LLMMessage(
                                role=MessageRole.TOOL,
                                content=tr["content"],
                                tool_call_id=tr["call_id"],
                            )
                        )

                    # Update conversation with new messages
                    conversation = [
                        LLMMessage(role=MessageRole.SYSTEM, content=system_message),
                        *self.messages,
                    ]

                    # Generate follow-up response with updated conversation
                    with self.console.status(
                        "[dim]🤔 Analyzing results...[/dim]", spinner="dots"
                    ):
                        follow_up_response = await self.provider.generate(
                            messages=conversation, tools=tools, stream=False
                        )

                    # Display thinking blocks from follow-up
                    self._display_thinking(follow_up_response.thinking_blocks)

                    # Use the follow-up response content
                    if follow_up_response.content:
                        response.content = follow_up_response.content
                        response.usage = follow_up_response.usage  # Update usage stats

            # Display response
            if response.content:
                # Add a visual separator before response
                self.console.print()
                self.console.print(Markdown(response.content))
                self.messages.append(
                    LLMMessage(role=MessageRole.ASSISTANT, content=response.content)
                )

            # Display token usage
            self._display_token_usage(response.usage)

        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")

    def _prepare_system_message(self) -> str:
        """Prepare system message with context."""
        functions_desc = []
        for func in function_registry.list_all():
            schema = func.get_schema()
            params = []
            if "properties" in schema:
                for param, details in schema["properties"].items():
                    required = param in schema.get("required", [])
                    params.append(
                        f"  - {param}: {details.get('type', 'any')}"
                        f"{' (required)' if required else ''}"
                    )

            functions_desc.append(
                f"- {func.name}: {func.description}\n" + "\n".join(params)
                if params
                else ""
            )

        return f"""You are a KubeStellar agent for multi-cluster Kubernetes management. You provide accurate, structured responses based on real data.

## Function Usage Guide:
- Pod counts → `namespace_utils` with `operation="list"`, `resource_types=["pods"]`, `include_resources=true`, `all_namespaces=true`
- Cluster info → `get_kubeconfig` or `deploy_to` with `list_clusters=true`
- Logs → `multicluster_logs`
- Resources → `gvrc_discovery`

## Available Functions:
{chr(10).join(functions_desc)}

## Response Requirements:
1. **Answer the exact question asked**
2. **Use ONLY data from function results - never fabricate information**
3. **Present data in clean, structured format:**

For pod counts, respond like this:
```
**Total Pods: X across Y clusters**

| Cluster | Pods | Status |
|---------|------|--------|
| cluster1| 12   | Ready  |
| its1    | 8    | Ready  |

**Summary:** Brief summary if helpful
```

## Critical Rules:
- Parse JSON function results carefully to extract actual data
- Use real cluster names from the results (cluster1, cluster2, its1, kind-kubeflex, etc.)
- Count actual resources in the data
- If data shows namespaces only, state that pod count data is not available
- Never guess or make up numbers
- Present information clearly and concisely"""

    async def run(self):
        """Run the interactive chat loop."""
        # ASCII art for KubeStellar with proper formatting
        self.console.print()
        self.console.print("[cyan]╭─────────────────────────────────────────────────────────────────────────────────────────────╮[/cyan]")
        self.console.print("[cyan]│[/cyan]                                                                                             [cyan]│[/cyan]")
        self.console.print("[cyan]│[/cyan]  [bold cyan]██╗  ██╗██╗   ██╗██████╗ ███████╗███████╗████████╗███████╗██╗     ██╗      █████╗ ██████╗[/bold cyan]  [cyan]│[/cyan]")
        self.console.print("[cyan]│[/cyan]  [bold cyan]██║ ██╔╝██║   ██║██╔══██╗██╔════╝██╔════╝╚══██╔══╝██╔════╝██║     ██║     ██╔══██╗██╔══██╗[/bold cyan] [cyan]│[/cyan]")
        self.console.print("[cyan]│[/cyan]  [bold cyan]█████╔╝ ██║   ██║██████╔╝█████╗  ███████╗   ██║   █████╗  ██║     ██║     ███████║██████╔╝[/bold cyan] [cyan]│[/cyan]")
        self.console.print("[cyan]│[/cyan]  [bold cyan]██╔═██╗ ██║   ██║██╔══██╗██╔══╝  ╚════██║   ██║   ██╔══╝  ██║     ██║     ██╔══██║██╔══██╗[/bold cyan] [cyan]│[/cyan]")
        self.console.print("[cyan]│[/cyan]  [bold cyan]██║  ██╗╚██████╔╝██████╔╝███████╗███████║   ██║   ███████╗███████╗███████╗██║  ██║██║  ██║[/bold cyan] [cyan]│[/cyan]")
        self.console.print("[cyan]│[/cyan]  [bold cyan]╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚══════╝   ╚═╝   ╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝[/bold cyan] [cyan]│[/cyan]")
        self.console.print("[cyan]│[/cyan]                                                                                             [cyan]│[/cyan]")
        self.console.print("[cyan]│[/cyan]                       [dim]🌟 Multi-Cluster Kubernetes Management Agent 🌟[/dim]                       [cyan]│[/cyan]")
        self.console.print("[cyan]╰─────────────────────────────────────────────────────────────────────────────────────────────╯[/cyan]")
        self.console.print()

        # Welcome message
        self.console.print(
            Panel(
                f"[bold]Welcome to KubeStellar Agent![/bold]\n\n"
                f"🚀 [bold cyan]KubeStellar[/bold cyan] is a multi-cluster configuration management platform\n"
                f"   that enables workload distribution across Kubernetes clusters.\n\n"
                f"🔧 This agent helps you:\n"
                f"   • [green]Discover[/green] and [green]analyze[/green] KubeStellar topologies\n"
                f"   • [green]Manage[/green] binding policies and work statuses\n"
                f"   • [green]Monitor[/green] multi-cluster resource distribution\n"
                f"   • [green]Perform[/green] deep searches across WDS, ITS, and WEC spaces\n\n"
                f"⚙️  Provider: [cyan]{self.provider_name}[/cyan]\n"
                f"🤖 Model: [cyan]{self.provider.config.model}[/cyan]\n\n"
                f"💡 Type [yellow]'help'[/yellow] for available commands\n"
                f"🚪 Type [yellow]'exit'[/yellow] or [yellow]Ctrl+D[/yellow] to quit",
                title="🌟 KubeStellar Multi-Cluster Agent",
                border_style="blue",
                padding=(1, 2),
            )
        )

        # Main loop
        while True:
            try:
                # Get user input
                user_input = await asyncio.to_thread(
                    self.session.prompt,
                    self._format_prompt(),
                    style=self.prompt_style,
                )

                # Handle special commands
                if user_input.lower() in ["exit", "quit", "q"]:
                    break
                elif user_input.lower() == "help":
                    self._show_help()
                    continue
                elif user_input.lower() == "clear":
                    self.messages.clear()
                    self.console.clear()
                    continue
                elif user_input.lower().startswith("provider "):
                    self._switch_provider(user_input.split()[1])
                    continue
                elif user_input.strip() == "":
                    continue

                # Handle message
                await self._handle_message(user_input)

            except (EOFError, KeyboardInterrupt):
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")

        # Goodbye
        self.console.print("\n[dim]Goodbye![/dim]")

    def _show_help(self):
        """Show help message."""
        help_text = """
[bold]Available Commands:[/bold]

• [cyan]help[/cyan] - Show this help message
• [cyan]clear[/cyan] - Clear conversation history
• [cyan]provider <name>[/cyan] - Switch to a different provider
• [cyan]exit[/cyan] - Exit the agent

[bold]Available Functions:[/bold]
"""
        self.console.print(help_text)

        # List functions
        for func in function_registry.list_all():
            self.console.print(f"• [green]{func.name}[/green] - {func.description}")

    def _switch_provider(self, provider_name: str):
        """Switch to a different provider."""
        try:
            self._setup_provider(provider_name)
            self.console.print(f"[green]Switched to {provider_name}[/green]")
        except Exception as e:
            self.console.print(f"[red]Failed to switch provider: {e}[/red]")
