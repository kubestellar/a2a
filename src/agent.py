"""Interactive agent mode for a2a CLI."""

import asyncio
import json
import sys
import time
from typing import Any, Awaitable, Dict, List, Optional, TypeVar

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from src.llm_providers import (
    BaseLLMProvider,
    LLMMessage,
    MessageRole,
    ProviderConfig,
    get_provider,
)
from src.llm_providers.config import get_config_manager
from src.shared.base_functions import function_registry
from src.shared.functions import initialize_functions

T = TypeVar('T')

class AgentChat:
    """Interactive agent chat interface."""

    def __init__(self, provider_name: Optional[str] = None):
        """Initialize agent chat."""
        self.console = Console()
        self.config_manager = get_config_manager()
        self.messages: List[LLMMessage] = []
        self.provider: Optional[BaseLLMProvider] = None
        # Ensure stdin is non-blocking for prompt-toolkit and our escape logic
        if sys.stdin and sys.stdin.isatty():
            import termios
            import tty
            self._old_tty_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())

        self.session = PromptSession(
            history=FileHistory(str(self.config_manager.config_dir / "chat_history"))
        )
        self.plan: Optional[List[Dict[str, Any]]] = None

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

    async def _wait_for_escape(self) -> None:
        """
        Block until the user presses the Escape key.
        Runs in the event-loop, uses add_reader so it works while
        other coroutines are running.
        """
        if not sys.stdin.isatty():
            await asyncio.Future() # block indefinitely if not a TTY
            return

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()

        def _on_key_press() -> None:          # called by add_reader
            # Non-blocking read
            try:
                ch = sys.stdin.read(1)            # read one raw byte
                if ch == "\x1b":                  # ESC
                    if not fut.done():
                        fut.set_result(None)
            except OSError:
                # Handle case where read may fail (e.g., race condition on closing)
                pass

        loop.add_reader(sys.stdin.fileno(), _on_key_press)
        try:
            await fut                         # wait until ESC pressed
        finally:
            loop.remove_reader(sys.stdin.fileno())

    async def _run_with_cancel(self, coro: Awaitable[T]) -> Optional[T]:
        """
        Run *coro* and listen for ESC simultaneously.
        If ESC is pressed first, cancel the task and return None.
        Otherwise return the coroutine’s result.
        """
        task = asyncio.create_task(coro)
        esc  = asyncio.create_task(self._wait_for_escape())

        done, _ = await asyncio.wait({task, esc},
                                     return_when=asyncio.FIRST_COMPLETED)

        if esc in done:                       # user hit ESC
            task.cancel()
            self.console.print("[yellow]⏹  Operation cancelled (ESC)[/yellow]")
            try:
                await task                    # swallow CancelledError
            except asyncio.CancelledError:
                pass
            return None
        else:                                 # task finished normally
            esc.cancel()
            return await task

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

    async def _execute_function(self, function_name: str, args: Dict[str, Any]) -> tuple[str, float]:
        """Execute a KubeStellar function."""
        function = function_registry.get(function_name)
        if not function:
            return f"Error: Unknown function '{function_name}'",0.0

        try:
            start = time.perf_counter()
            result_dict = await function.execute(**args)
            elapsed = time.perf_counter() - start
            return json.dumps(result_dict, indent=2), elapsed
        except Exception as e:
            return f"Error executing {function_name}: {str(e)}", 0.0


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
        if self.plan and user_input.lower() in ["yes", "y"]:
            await self._execute_plan()
            return

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
                response = await self._run_with_cancel(
                    self.provider.generate(
                        messages=conversation,
                        tools=tools, 
                        stream=False,  
                    )
                )
            if response is None:
                return

            # Display thinking blocks
            self._display_thinking(response.thinking_blocks)

            # Handle tool calls
            if response.tool_calls:
                if response.tool_calls[0].name == "create_plan":
                    self.plan = response.tool_calls[0].arguments["steps"]
                    self._present_plan()
                    return

                tool_results = []
                for tool_call in response.tool_calls:
                    if tool_call.name:  # Only execute if function name is not empty
                        # Show function execution with spinner
                        with self.console.status(
                            f"[dim]⚙️  Executing: {tool_call.name}[/dim]", spinner="dots"
                        ):
                            result,elapsed = await self._run_with_cancel(
                                self._execute_function(tool_call.name, tool_call.arguments)
                            )
                        if result is None:        
                            return
                        
                        tool_results.append(
                            {"call_id": tool_call.id, "content": result}
                        )

                        # Display completion
                        self.console.print(
                            f"[green]✓[/green] [dim]Completed: {tool_call.name} "
                            f"({elapsed:.3f}s)[/dim]"
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
                        follow_up_response = await self._run_with_cancel(
                            self.provider.generate(
                                messages=conversation, tools=tools, stream=False
                            )
                        )

                    if follow_up_response is None:
                        return

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
- Specific resource by name → `namespace_utils` with `operation="list-resources"`, `resource_types=["<resource_type>"]`, `resource_name="<resource_name>"`, `all_namespaces=true`
- Cluster info → `get_kubeconfig` or `deploy_to` with `list_clusters=true`
- Logs → `multicluster_logs`
- Resources → `gvrc_discovery`

## Available Functions:
{chr(10).join(functions_desc)}

## Tool Usage Strategy:
- **For simple tasks** that can be solved with a single function call, call the function directly. Do NOT create a plan.
- **For complex tasks** that require multiple, sequential function calls, you MUST use the `create_plan` function. The plan should be a sequence of function calls to achieve the user's goal.

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

    def _present_plan(self):
        """Present the execution plan to the user for approval."""
        if not self.plan:
            return

        self.console.print("\n[bold]Execution Plan:[/bold]")
        for i, step in enumerate(self.plan):
            self.console.print(
                f"  [cyan]{i+1}.[/cyan] [bold]{step['function_name']}[/bold]"
            )
            for key, value in step["arguments"].items():
                self.console.print(f"     - {key}: {value}")
        self.console.print("\nDo you want to execute this plan? (yes/no)")

    async def _execute_plan(self):
        """Execute the approved plan."""
        if not self.plan:
            return

        tool_results = []
        for i, step in enumerate(self.plan):
            with self.console.status(
                f"[dim]⚙️  Executing step {i+1}/{len(self.plan)}: {step['function_name']}[/dim]",
                spinner="dots",
            ):
                result, elapsed = await self._execute_function(
                    step["function_name"], step["arguments"]
                )

            # Check for errors
            if result.strip().startswith("Error:"):
                self.console.print(
                    f"[red]✗[/red] [bold red]Error in step {i+1} ({step['function_name']}):[/bold red]"
                )
                self.console.print(f"[red]{result.strip()}[/red]")
                self.console.print("[yellow]Plan execution aborted.[/yellow]")
                self.plan = None  # Clear the plan
                return

            tool_results.append({"call_id": f"plan_step_{i}", "content": result})
            self.console.print(
                f"[green]✓[/green] [dim]Completed: {step['function_name']} "
                f"({elapsed:.3f}s)[/dim]"
            )

            # Summarize and display the result of the step
            with self.console.status(
                "[dim]📝 Summarizing result...[/dim]", spinner="dots"
            ):
                summary = await self._summarize_result(step["function_name"], result)

            self.console.print(
                Panel(
                    summary.strip(),
                    title=f"Summary from {step['function_name']}",
                    border_style="blue",
                    padding=(1, 2),
                    expand=False,
                )
            )

        self.plan = None  # Clear the plan after execution

        # Process the results
        if tool_results:
            self.console.print("[dim]📊 Processing data...[/dim]")
            for tr in tool_results:
                self.messages.append(
                    LLMMessage(
                        role=MessageRole.TOOL,
                        content=tr["content"],
                        tool_call_id=tr["call_id"],
                    )
                )

            system_message = self._prepare_system_message()
            conversation = [
                LLMMessage(role=MessageRole.SYSTEM, content=system_message),
                *self.messages,
            ]
            tools = self._prepare_tools()

            with self.console.status(
                "[dim]🤔 Analyzing results...[/dim]", spinner="dots"
            ):
                follow_up_response = await self.provider.generate(
                    messages=conversation, tools=tools, stream=False
                )

            self._display_thinking(follow_up_response.thinking_blocks)

            if follow_up_response.content:
                self.console.print()
                self.console.print(Markdown(follow_up_response.content))
                self.messages.append(
                    LLMMessage(
                        role=MessageRole.ASSISTANT, content=follow_up_response.content
                    )
                )

            self._display_token_usage(follow_up_response.usage)

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
                f"⚙️  Provider: [cyan]{self.provider_name.capitalize()}[/cyan]\n"
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

        if sys.stdin and sys.stdin.isatty():
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_tty_settings)
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

    async def _summarize_result(self, function_name: str, result: str) -> str:
        """Summarize the result of a tool execution using the LLM."""
        try:
            prompt = f'''Please summarize the following JSON output from the `{function_name}` tool.
Focus on the most important information for the user, such as success or failure, names of created resources, or key data points.
Keep the summary concise and easy to read.

Tool Output:
```json
{result}
```'''
            messages = [LLMMessage(role=MessageRole.USER, content=prompt)]

            # We don't want the summarizer to call tools, so pass an empty list.
            response = await self.provider.generate(
                messages=messages, tools=[], stream=False
            )

            summary = response.content
            if not summary:
                return "Could not generate a summary."

            # Also display token usage for this summary call
            self._display_token_usage(response.usage)

            return summary

        except Exception as e:
            return f"Error summarizing result: {e}"
