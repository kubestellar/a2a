"""Interactive agent mode for a2a CLI."""

import asyncio
import json
import signal
import sys
import time
from typing import Any, Awaitable, Dict, List, Optional, TypeVar

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
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
from src.shared.task_queue import TaskPriority, task_executor

T = TypeVar("T")


def _json_serializer(obj: Any) -> Any:
    """Custom JSON serializer to handle complex objects like MapComposite."""
    if obj is None:
        return None

    # explicit type check for protobuf objects
    type_str = str(type(obj))
    if "MapComposite" in type_str and hasattr(obj, "items"):
        try:
            return dict(obj.items())
        except Exception:
            pass
    if "RepeatedComposite" in type_str and hasattr(obj, "__iter__"):
        try:
            return list(obj)
        except Exception:
            pass

    if hasattr(obj, "__class__"):
        class_name = str(obj.__class__)
        # Check for protobuf MapComposite or similar mapping objects
        if "MapComposite" in class_name or "Mapping" in class_name:
            try:
                # First try direct conversion to dict
                if hasattr(obj, "items"):
                    return dict(obj.items())
                # For protobuf repeated fields or other iterables
                return {k: v for k, v in obj.items()}
            except Exception:
                pass  # Fall through to string representation

        # Handle other objects that might be mappable
        if not isinstance(obj, (str, int, float, bool, type(None))):
            try:
                # Try to convert to dict if it has items() method
                if hasattr(obj, "items") and callable(getattr(obj, "items")):
                    return dict(obj.items())
            except (TypeError, AttributeError, ValueError):
                pass

    # Default: convert to string
    return str(obj)


class AgentChat:
    """Interactive agent chat interface."""

    def __init__(self, provider_name: Optional[str] = None):
        """Initialize agent chat."""
        self.console = Console()
        self.config_manager = get_config_manager()
        self.messages: List[LLMMessage] = []
        self.provider: Optional[BaseLLMProvider] = None

        # Track running tasks for cancellation
        self._running_tasks: set[asyncio.Task] = set()
        self._current_task: Optional[asyncio.Task] = None

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
            await asyncio.Future()  # block indefinitely if not a TTY
            return

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()

        def _on_key_press() -> None:  # called by add_reader
            # Non-blocking read
            try:
                ch = sys.stdin.read(1)  # read one raw byte
                if ch == "\x1b":  # ESC
                    if not fut.done():
                        fut.set_result(None)
            except OSError:
                # Handle case where read may fail (e.g., race condition on closing)
                pass

        loop.add_reader(sys.stdin.fileno(), _on_key_press)
        try:
            await fut  # wait until ESC pressed
        finally:
            loop.remove_reader(sys.stdin.fileno())

    def _cancel_all_tasks(self):
        """Cancel all running tasks."""
        for task in self._running_tasks:
            if not task.done():
                task.cancel()
        self._running_tasks.clear()

        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            self._current_task = None

    async def _run_with_cancel(self, coro: Awaitable[T]) -> Optional[T]:
        """
        Run *coro* and listen for ESC or Ctrl+C simultaneously.
        If ESC or Ctrl+C is pressed first, cancel the task and return None.
        Otherwise return the coroutine's result.
        """
        task = asyncio.create_task(coro)
        self._current_task = task
        self._running_tasks.add(task)

        try:
            esc = asyncio.create_task(self._wait_for_escape())
            self._running_tasks.add(esc)

            done, _ = await asyncio.wait(
                {task, esc}, return_when=asyncio.FIRST_COMPLETED
            )

            if esc in done:  # user hit ESC
                task.cancel()
                self.console.print("[yellow]⏹  Operation cancelled (ESC)[/yellow]")
                try:
                    await task  # swallow CancelledError
                except asyncio.CancelledError:
                    pass
                return None
            else:  # task finished normally
                esc.cancel()
                return await task
        finally:
            self._running_tasks.discard(task)
            self._running_tasks.discard(esc)
            self._current_task = None

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

    async def _execute_function(
        self,
        function_name: str,
        args: Dict[str, Any],
        *,
        priority: TaskPriority = TaskPriority.MEDIUM,
    ) -> tuple[str, float]:
        """Execute a KubeStellar function."""
        function = function_registry.get(function_name)
        if not function:
            return f"Error: Unknown function '{function_name}'", 0.0

        try:
            start = time.perf_counter()
            result_dict = await task_executor.run_function(
                function, args, priority=priority
            )
            elapsed = time.perf_counter() - start
            return json.dumps(result_dict, indent=2, default=_json_serializer), elapsed
        except Exception as e:
            return f"Error executing {function_name}: {str(e)}", 0.0

    def _prepare_tools(self) -> List[Dict[str, Any]]:
        """Prepare available tools for the LLM."""
        tools = []
        for function in function_registry.list_all():
            schema = function.get_schema()
            # Ensure schema is JSON-serializable by converting any complex objects
            try:
                import json

                # Serialize and deserialize to ensure clean JSON objects
                clean_schema = json.loads(json.dumps(schema, default=_json_serializer))
            except (TypeError, ValueError):
                clean_schema = schema

            tools.append(
                {
                    "name": function.name,
                    "description": function.description,
                    "inputSchema": clean_schema,
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

                    # Validate plan before presenting to user
                    if not self._validate_plan():
                        # Don't present invalid plan, let LLM regenerate
                        return

                    self._present_plan()
                    return

                tool_results = []
                for tool_call in response.tool_calls:
                    if tool_call.name:  # Only execute if function name is not empty
                        # Show function execution with spinner
                        with self.console.status(
                            f"[dim]⚙️  Executing: {tool_call.name}[/dim]", spinner="dots"
                        ):
                            result, elapsed = await self._run_with_cancel(
                                self._execute_function(
                                    tool_call.name, tool_call.arguments
                                )
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

            func_desc = f"- {func.name}: {func.description}"
            if params:
                func_desc += "\n" + "\n".join(params)
            functions_desc.append(func_desc)

        return (
            """⚠️⚠️⚠️ URGENT: JSON STRINGS MUST BE QUOTED ⚠️⚠️⚠️
ALWAYS use: {"key": "value"} NEVER: {"key": value}
Examples: {"app": "my-app"}, {"workload-type": "batch"}

You are a KubeStellar agent for multi-cluster Kubernetes management. You provide accurate, structured responses based on real data.

## ⚠️ CRITICAL JSON FORMATTING RULES - READ FIRST:
- ALL string values in JSON must be DOUBLE-QUOTED: {"key": "value"}
- NEVER use unquoted strings: {"key": value} ❌ WRONG
- Labels ALWAYS need quotes: {"app": "my-app"} ✅ RIGHT
- Selector labels: {"workload-type": "batch"} ✅ RIGHT
- EXAMPLES:
  ❌ WRONG: {"app.kubernetes.io/part-of": my-appwrapper-app}
  ✅ RIGHT: {"app.kubernetes.io/part-of": "my-appwrapper-app"}
  ❌ WRONG: {"workload-type": batch}
  ✅ RIGHT: {"workload-type": "batch"}

## Function Usage Guide:
- **Pod counts** → `namespace_utils` with `operation="list"`, `resource_types=["pods"]`, `include_resources=true`, `all_namespaces=true`
- **Specific resource by name** → `namespace_utils` with `operation="list-resources"`, `resource_types=["<resource_type>"]`, `resource_name="<resource_name>"`, `all_namespaces=true`
- **Cluster info** → `get_kubeconfig` or `deploy_to` with `list_clusters=true`
- **Download manifests** → `fetch_manifest` (downloads YAML/JSON from URLs)
- **Apply resources** → `deploy_to` (applies YAML files to clusters, supports labels)
- **Helm deployments** → `helm_deploy` (for Helm charts only)
- **Binding policies** → `binding_policy_management` (create/manage BindingPolicies)
- **Cluster management** → `cluster_management` (register/label clusters in WDS or ITS contexts)
  - Use `context="its1"` for WEC cluster registration (creates ManagedCluster)
  - Use `context="wds1"` for WDS cluster management (creates Bindings)
  - Supports label-based queries and cluster listing
- **Logs** → `multicluster_logs`
- **Resources** → `gvrc_discovery`

## IMPORTANT: Tool Selection Rules:
- **NEVER hallucinate tools** - Only use tools listed in the Available Functions section
- **For applying YAML files** → Always use `deploy_to`, never `multicluster_create` (which doesn't exist)
- **For downloading from URLs** → Use `fetch_manifest`
- **For CRDs and Custom Resources** → Use `apiextensions.k8s.io/customresourcedefinitions` as resource type
- **JSON values must be quoted** → Use {"key": "value"} not {"key": value}
- **String values in labels** → Always use quotes: {"app": "my-app"} not {"app": my-app}
- **CRITICAL: All string values in JSON must be double-quoted** → {"key": "string-value"} never {"key": string-value}

## WDS vs ITS Context Rules - CRITICAL:
- **WDS context** → For deploying operators, CRDs, and workload definitions (e.g., KubeVirt operator)
- **ITS context** → For registering worker execution clusters (WECs) only
- **Deploy operators/CRDs** → Always use `context="wds1"` or WDS clusters
- **Register clusters** → Use `context="its1"` for WEC registration
- **NEVER deploy operators to ITS** → ITS is for cluster management, not workload operators

## ⚠️ DEPLOY_TO CRITICAL FIXES:
- **ALWAYS specify target_clusters**: Use ["its1"] for KubeStellar workflows
- **Smart default available**: If no target specified, will auto-select ITS cluster
- **Explicit targeting preferred**: Always specify target_clusters for clarity
- **KubeStellar workflow**: Deploy to ITS first, then use BindingPolicy for distribution

## Advanced BindingPolicy Features:
- **cluster_selectors** → Use for cluster targeting: [{"virtualization": "enabled"}]
- **custom_transform** → Use to exclude fields: {"exclude_fields": ["spec.suspend"]}
- **status_collectors** → Use for status aggregation: [{"resource": "virtualmachines", "fields": ["status.phase"]}]
- **selector_labels** → OLD parameter, use cluster_selectors instead
- **ALWAYS include advanced features** when specified in request

## ⚠️ BINDINGPOLICY CRITICAL FIXES:
- **Parameter name**: Use `context="wds1"` NOT `wds_context`
- **cluster_selectors format**: Use proper JSON: [{"matchLabels": {"app": "myapp"}}]
- **Never use selector_labels**: Use cluster_selectors for cluster targeting
- **MapComposite objects**: Will be auto-converted, but ensure proper JSON format
- **resources**: MUST be provided for quick_create (e.g. ['apps/deployments'])
- **ALWAYS specify resources**: Required for quick_create operation to function

## CRD and Custom Resource Handling:
- **CRD resource type** → Always use "apiextensions.k8s.io/customresourcedefinitions"
- **Custom resource types** → Use format: "api.group/resource" (e.g., "workload.codeflare.dev/appwrappers")
- **AppWrapper CRD** → Resource type: "workload.codeflare.dev/appwrappers"
- **Verification** → Use `namespace_utils` with `resource_types=["customresourcedefinitions"]` to verify CRD installation
- **CRD vs Instance**: CRDs define resource types, instances use those types. Install CRD first, then instances.

## JSON FORMATTING - CRITICAL RULES:
- **ALL string values must be quoted**: {"name": "my-app"} not {"name": my-app}
- **Labels are objects**: {"app.kubernetes.io/part-of": "my-app"} not {"app.kubernetes.io/part-of": my-app}
- **Selector labels**: {"workload-type": "batch"} not {"workload-type": batch}
- **Array values**: ["item1", "item2"] with quotes for strings
- **Boolean values**: true/false (no quotes)
- **Numeric values**: 123, 45.6 (no quotes)

## COMMON JSON MISTAKES - AVOID THESE:
❌ **WRONG**: {"app.kubernetes.io/part-of": my-appwrapper-app}
✅ **RIGHT**: {"app.kubernetes.io/part-of": "my-appwrapper-app"}

❌ **WRONG**: {"workload-type": batch}
✅ **RIGHT**: {"workload-type": "batch"}

❌ **WRONG**: {"environment": production, "tier": frontend}
✅ **RIGHT**: {"environment": "production", "tier": "frontend"}

❌ **WRONG**: selector_labels={"location-group": edge}
✅ **RIGHT**: selector_labels={"location-group": "edge"}

**REMEMBER: If it's text, it needs quotes!**

## ⚠️ FINAL WARNING: CHECK YOUR JSON FORMATTING:
Before executing any plan, verify ALL string values are quoted:
- labels: {"app.kubernetes.io/part-of": "my-appwrapper-app"} ✅
- selector_labels: {"workload-type": "batch"} ✅
- NEVER: {"key": unquoted-value} ❌

## ⚠️ FINAL CRITICAL WARNINGS - READ EVERY TIME:
- **WDS vs ITS**: Deploy operators/CRDs to WDS, register clusters to ITS
- **JSON Quotes**: ALL string values must be double-quoted: {"key": "value"}
- **Advanced Features**: Always include custom_transform and status_collectors when requested
- **Parameter Names**: Use cluster_selectors (not selector_labels) for cluster targeting
- **Context Selection**: context="wds1" for workloads, context="its1" for cluster registration

## Kubernetes Labels Explained:
Labels are key-value pairs attached to Kubernetes objects that help organize and select resources. Common label patterns:

- **app.kubernetes.io/name**: Application name (e.g., "nginx", "postgres")
- **app.kubernetes.io/component**: Component within an application (e.g., "database", "frontend")
- **environment**: Deployment environment (e.g., "production", "staging", "development")
- **version**: Application version (e.g., "v1.0.0", "latest")
- **location-group**: Geographic or logical grouping for multi-cluster setups

**Why labels matter:**
- **Selection**: Use label selectors to filter resources (kubectl get pods -l app=nginx)
- **Binding Policies**: KubeStellar uses labels to determine which objects bind to which clusters
- **Organization**: Group related resources for management and monitoring
- **Deployment**: Control where workloads get deployed based on cluster labels

## Tool Usage Examples:

### Complex BindingPolicy Example (CORRECT):
```
# Create advanced BindingPolicy with matchLabels + matchExpressions
binding_policy_management(
    operation="quick_create",
    policy_name="myapp-policy",
    context="wds1",  # ✅ CORRECT: use context, NOT wds_context
    cluster_selectors=[  # ✅ CORRECT: use cluster_selectors, NOT selector_labels
        {"matchLabels": {"app": "myapp"}},
        {"matchExpressions": [
            {"key": "region", "operator": "In", "values": ["us-east", "us-west"]},
            {"key": "environment", "operator": "Equals", "values": ["prod"]}
        ]}
    ],
    custom_transform={"exclude_fields": ["spec.suspend"]},
    status_collectors=[{"resource": "deployments", "fields": ["status.phase"]}],
    resources=["apps/deployments", "core/services"]
)
```

### KubeVirt Deployment Example (CORRECT):
```
# 1. Deploy KubeVirt operator to WDS (CORRECT)
deploy_to(
    context="wds1",
    filename="/tmp/kubevirt-operator.yaml",
    labels={"deploy": "kubevirt"}
)

# 2. Create advanced BindingPolicy (CORRECT)
binding_policy_management(
    operation="quick_create",
    policy_name="kubevirt-policy",
    cluster_selectors=[{"virtualization": "enabled"}],
    custom_transform={"exclude_fields": ["spec.suspend"]},
    status_collectors=[{"resource": "virtualmachines", "fields": ["status.phase"]}],
    resources=["kubevirt.io/virtualmachines", "kubevirt.io/virtualmachineinstances"]
)

# 3. WRONG - Never deploy operators to ITS
deploy_to(
    target_clusters=["its1"],  # ❌ WRONG - ITS is for cluster registration
    filename="/tmp/kubevirt-operator.yaml"
)
```

### deploy_to Tool:
Deploy resources to specific named clusters, clusters matching labels, or all clusters in a WDS context. Perfect for edge deployments, staging environments, or when you need workloads only on certain clusters.

**Arguments:**
- `target_clusters`: Array of cluster names (e.g., ['its1'], ['cluster1', 'cluster2'])
- `cluster_labels`: Array of label selectors for cluster targeting in key=value format (e.g., ['location-group=edge'])
- `context`: WDS context name to deploy to all clusters in that context (e.g., 'wds1')
- `filename`: Path to YAML/JSON file containing resource definitions
- `resource_type`: Type of resource to create when not using filename (deployment, service, configmap, secret, namespace)
- `resource_name`: Name of resource to create when not using filename
- `image`: Global image override for deployments
- `cluster_images`: Array of per-cluster image overrides in cluster=image format (e.g., ['cluster1=nginx:1.0', 'cluster2=nginx:2.0'])
- `labels`: Object of key/value pairs to label resources after deployment (e.g., {"app.kubernetes.io/name": "nginx", "environment": "production"})
- `namespace`: Namespace to deploy resources to (default: 'default'). For KubeVirt operator, use 'kubevirt'.
- `dry_run`: If true, only show what would be deployed without making changes
- `list_clusters`: If true, list available clusters and their status

**IMPORTANT**: When deploying KubeVirt operator, ALWAYS specify `namespace='kubevirt'` as the operator requires this namespace.

**Example:**
```
deploy_to(
    target_clusters=['its1'],
    filename='/tmp/nginx-deployment.yaml',
    labels={"app.kubernetes.io/name": "nginx", "environment": "production"}
)
```

**Example with context:**
```
deploy_to(
    context='wds1',
    filename='/tmp/nginx-deployment.yaml',
    labels={"app.kubernetes.io/name": "nginx", "environment": "production"}
)
```

**Example (download and apply CRD):**
```
# Step 1: Download CRD from URL
fetch_manifest(
    url="https://raw.githubusercontent.com/example/crd.yaml",
    destination="/tmp/appwrapper-crd.yaml"
)

# Step 2: Apply CRD to WDS with labels
deploy_to(
    context='wds1',
    filename='/tmp/appwrapper-crd.yaml',
    labels={"app.kubernetes.io/part-of": "my-appwrapper-app"}
)
```

**Example (BindingPolicy with proper JSON):**
```
binding_policy_management(
    operation='quick_create',
    policy_name='appwrapper-crd-policy',
    selector_labels={"workload-type": "batch"},
    resources=["workload.codeflare.dev/appwrappers"]
)
```

### fetch_manifest Tool:
Download remote manifests (YAML/JSON) from URLs and save them locally for deployment. Supports single files, multiple files, or entire directory structures from GitHub repositories.

**Arguments:**
- `url`: Single URL of the manifest to download (backward compatibility)
- `urls`: List of multiple URLs to download (for bulk operations)
- `base_url`: Base GitHub repository URL (e.g., 'https://github.com/user/repo/tree/main')
- `directories`: List of directories to scan (e.g., ['deployments', 'services', 'configmaps'])
- `file_patterns`: File patterns to match (default: ['*.yaml', '*.yml'])
- `destination`: Local path where to save downloaded manifests (optional)
- `headers`: HTTP headers to include in the request (optional)
- `insecure_skip_tls_verify`: Skip TLS verification for HTTPS (default: false)

**Usage Options:**
1. **Single file**: Use `url` parameter
2. **Multiple files**: Use `urls` parameter with list of URLs
3. **Directory bulk**: Use `base_url` + `directories` for GitHub repos

**Example (single file):**
```
fetch_manifest(
    url="https://raw.githubusercontent.com/example/crd.yaml",
    destination="/tmp/appwrapper-crd.yaml"
)
```

**Example (multiple files):**
```
fetch_manifest(
    urls=[
        "https://raw.githubusercontent.com/user/repo/main/deployments/app.yaml",
        "https://raw.githubusercontent.com/user/repo/main/services/app.yaml",
        "https://raw.githubusercontent.com/user/repo/main/configmaps/app.yaml"
    ],
    destination="/tmp/manifests/"
)
```

**Example (GitHub directory bulk download):**
```
fetch_manifest(
    base_url="https://github.com/user/repo/tree/main",
    directories=["deployments", "services", "configmaps", "ingress"],
    destination="/tmp/myapp/",
    file_patterns=["*.yaml", "*.yml"]
)
```

**Returns:**
- `status`: success/error
- `total_files`: Number of files attempted
- `successful`: Number of successfully downloaded files
- `failed`: Number of failed downloads
- `downloaded_files`: List with details of each download
- `base_directory`: Where files were saved

### helm_deploy Tool:
Deploy Helm charts with KubeStellar multi-cluster support. For KubeStellar deployments, deploy to ITS cluster (e.g., its1) and create BindingPolicy in WDS (e.g., wds1) to propagate to WECs.

**Arguments:**
- `chart_name`: Name of the Helm chart (e.g., 'postgresql')
- `chart_version`: Version of the chart to deploy (e.g., '12.0.0')
- `repository_url`: Helm repository URL (e.g., 'https://charts.bitnami.com/bitnami')
- `repository_name`: Helm repository name (if already added)
- `chart_path`: Local path to chart directory or .tgz file
- `release_name`: Name of the Helm release
- `target_clusters`: Names of clusters to deploy to (for KubeStellar, use ITS cluster like ["its1"]). Do NOT use with cluster_selector_labels.
- `cluster_labels`: Label selectors for cluster targeting (alternative to target_clusters). Do NOT use with cluster_selector_labels.
- `namespace`: Target namespace for deployment (default: 'default')
- `values_file`: Path to values file
- `set_values`: Set values (key=value format)
- `create_namespace`: Create namespace if it doesn't exist (default: true)
- `wait`: Wait for deployment (use false to avoid timeouts)
- `operation`: Helm operation (install, upgrade, uninstall, status, history)
- `create_binding_policy`: Create KubeStellar binding policy (default: true)
- `binding_policy_name`: Name for the binding policy (auto-generated if empty)
- `cluster_selector_labels`: Labels to select WECs (e.g., {"environment": "prod"})
- `kubestellar_labels`: Additional labels for resources
- `wds_context`: WDS cluster context for policy creation (e.g., "wds1")

**Example (KubeStellar deployment to specific clusters):**
```
helm_deploy(
    chart_name="postgresql",
    chart_version="12.0.0",
    repository_url="https://charts.bitnami.com/bitnami",
    release_name="postgres",
    target_clusters=["its1"],
    namespace="postgres-system",
    create_namespace=True,
    wait=false,
    create_binding_policy=true,
    cluster_selector_labels={"location-group": "edge"},
    kubestellar_labels={"app.kubernetes.io/managed-by": "Helm", "app.kubernetes.io/instance": "postgres"},
    wds_context="wds1"
)
```

**Example (KubeStellar deployment using labels only):**
```
helm_deploy(
    chart_name="postgresql",
    chart_version="12.0.0",
    repository_url="https://charts.bitnami.com/bitnami",
    release_name="postgres",
    namespace="postgres-system",
    create_namespace=True,
    wait=false,
    create_binding_policy=true,
    cluster_selector_labels={"environment": "prod"},
    kubestellar_labels={"app.kubernetes.io/managed-by": "Helm", "app.kubernetes.io/instance": "postgres"},
    wds_context="wds1"
)
```

### cluster_management Tool:
Register and manage clusters in KubeStellar WDS or ITS contexts. Apply labels, list registered clusters, and manage cluster metadata. Supports both WEC cluster registration (ITS) and WDS cluster management.

**Arguments:**
- `operation`: Operation to perform - 'list', 'register', 'label', 'unregister', 'update-labels' (default: 'list')
- `cluster_name`: Name of the cluster to manage (required for most operations)
- `context`: Kubernetes context name where clusters are registered (WDS or ITS) (default: 'wds1')
- `labels`: Labels to apply to the cluster (key-value pairs)
- `kubeconfig`: Path to kubeconfig file

**Context Types:**
- **ITS contexts** (e.g., 'its1'): For WEC cluster registration - creates ManagedCluster resources
- **WDS contexts** (e.g., 'wds1'): For workload distribution - creates Binding resources

**Example (register WEC clusters to ITS):**
```
# Register WEC cluster1 with dev and gpu labels to ITS
cluster_management(
    operation='register',
    cluster_name='wec1',
    context='its1',
    labels={'environment': 'dev', 'region': 'us-east', 'gpu': 'enabled'}
)

# Register WEC cluster2 with staging labels to ITS
cluster_management(
    operation='register',
    cluster_name='wec2',
    context='its1',
    labels={'environment': 'staging', 'region': 'us-west'}
)
```

**Example (list clusters in different contexts):**
```
# List WEC clusters registered to ITS
cluster_management(operation='list', context='its1')

# List clusters in WDS context
cluster_management(operation='list', context='wds1')
```

**Example (label-based queries):**
```
# List clusters and filter by labels in results
cluster_management(operation='list', context='its1')
# Results include labels for filtering: {'environment': 'prod', 'gpu': 'enabled'}
```

### binding_policy_management Tool:
Fast operations on KubeStellar BindingPolicy objects (list, create, delete, quick_create) against a single WDS.

**Arguments:**
- `operation`: Operation type - 'list', 'create', 'delete', or 'quick_create' (default: 'list')
- `wds_context`: WDS context name (default: 'wds1')
- `kubeconfig`: Path to kubeconfig file
- `policy_name`: Name for the binding policy (required for create/delete)
- `policy_yaml`: Raw YAML manifest for create operation
- `policy_json`: JSON object for create operation
- `selector_labels`: Object of labels to select clusters (e.g., {"location-group": "edge"})
- `resources`: Array of resource types to bind (e.g., ['apps/deployments', 'core/namespaces'])
- `namespaces`: Array of namespaces where policy applies (e.g., ['default', 'production'])
- `specific_workloads`: Array of workload objects with apiVersion, kind, name, namespace fields. Use ONLY when you want to bind specific individual workloads instead of all resources matching labels. Omit this parameter when using selector_labels to bind all resources with certain labels.

**Example (binding all resources with labels):**
```
binding_policy_management(
    operation='quick_create',
    policy_name='nginx-bpolicy',
    selector_labels={"location-group": "edge"},
    resources=['apps/deployments'],
    namespaces=['default']
)
```

**Example (binding specific workloads only):**
```
binding_policy_management(
    operation='quick_create',
    policy_name='nginx-bpolicy',
    selector_labels={"location-group": "edge"},
    resources=['apps/deployments'],
    namespaces=['default'],
    specific_workloads=[{"apiVersion": "apps/v1", "kind": "Deployment", "name": "nginx", "namespace": "default"}]
)
```

**Example (advanced BindingPolicy with complex OR conditions):**
```
# Create policy for frontend OR backend clusters
# Target web-app OR api-service workloads
binding_policy_management(
    operation='quick_create',
    policy_name='multi-app-policy',
    cluster_selectors=[
        {"matchLabels": {"tier": "frontend"}},
        {"matchLabels": {"tier": "backend"}}
    ],
    object_selectors=[
        {"matchLabels": {"app": "web-app"}},
        {"matchLabels": {"app": "api-service"}}
    ],
    resources=['apps/deployments', 'core/services'],
    want_singleton_reported_state=True
)
```

**Note:** When using cluster_selectors or object_selectors, provide them as arrays of objects. Each selector object should have "matchLabels" with key-value pairs.

**CRITICAL clusterSelectors format**: ALWAYS use [{"matchLabels": {"key": "value"}}] format.
- ✅ CORRECT: [{"matchLabels": {"virtualization": "enabled"}}]
- ❌ WRONG: [{"virtualization": "enabled"}]

**Key Concept:** Binding policies connect workloads with specific labels to clusters with matching selector labels. Use `quick_create` for simple policies, or `create` with `policy_yaml` for complex ones.

## Available Functions:
"""
            + chr(10).join(functions_desc)
            + """

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
- Present information clearly and concisely
- When deploying resources, always explain the purpose of labels being applied"""
        )

    def _format_value(self, value: Any) -> str:
        """Format a value for display in the execution plan."""
        # Handle None
        if value is None:
            return "null"

        # Handle empty values
        if value == "":
            return '""'

        # Handle string representations of lists (common issue)
        if isinstance(value, str):
            # Check if it looks like a list representation
            if value.startswith("[") and value.endswith("]"):
                try:
                    # Try to parse as Python list
                    import ast

                    parsed_list = ast.literal_eval(value)
                    if isinstance(parsed_list, list):
                        formatted_items = [
                            self._format_value(item) for item in parsed_list
                        ]
                        result = "[" + ", ".join(formatted_items) + "]"
                        return result
                except (ValueError, SyntaxError):
                    pass  # Fall through to string handling

        # Handle dictionaries first (most common case)
        if isinstance(value, dict):
            formatted_items = []
            for k, v in value.items():
                # FIX: Always call _format_value recursively to handle MapComposite objects
                # This ensures MapComposite objects get processed by the specialized handlers below
                formatted_v = self._format_value(v)
                formatted_items.append(f'"{k}": {formatted_v}')
            return "{" + ", ".join(formatted_items) + "}"

        # Handle lists
        if isinstance(value, list):
            formatted_items = [self._format_value(item) for item in value]
            result = "[" + ", ".join(formatted_items) + "]"
            return result

        # CRITICAL FIX: Check for MapComposite/Mapping BEFORE generic iterables
        # MapComposite has __iter__ so it gets caught by the list check if we don't check it first
        type_str = str(type(value))
        if (
            "MapComposite" in type_str
            or "Mapping" in type_str
            or (hasattr(value, "items") and callable(getattr(value, "items")))
        ):
            try:
                if hasattr(value, "items"):
                    items = dict(value.items())
                    formatted_items = []
                    for k, v in items.items():
                        formatted_v = self._format_value(v)
                        formatted_items.append(f'"{k}": {formatted_v}')
                    result = "{" + ", ".join(formatted_items) + "}"
                    return result
            except Exception:
                pass

        # Handle protobuf RepeatedComposite (and other non-string iterables)
        if "RepeatedComposite" in type_str or (
            hasattr(value, "__iter__") and not isinstance(value, (str, bytes, dict))
        ):
            try:
                formatted_items = [self._format_value(item) for item in value]
                result = "[" + ", ".join(formatted_items) + "]"
                return result
            except Exception:
                pass

        # Handle other objects that might be mappable (legacy check, keep just in case)
        if not isinstance(value, (str, int, float, bool, type(None))):
            try:
                # Try to convert to dict if it has items() method
                if hasattr(value, "items") and callable(getattr(value, "items")):
                    items = dict(value.items())
                    formatted_items = []
                    for k, v in items.items():
                        formatted_v = self._format_value(v)
                        formatted_items.append(f'"{k}": {formatted_v}')
                    return "{" + ", ".join(formatted_items) + "}"
            except (TypeError, AttributeError, ValueError):
                pass

        # Default: convert to string
        return str(value)

    def _validate_plan(self):
        """Validate the execution plan for common issues before presenting to user."""
        if not self.plan:
            return True

        validation_errors = []

        for i, step in enumerate(self.plan):
            function_name = step.get("function_name", "")
            arguments = step.get("arguments", {})

            # Validate binding_policy_management quick_create requires resources
            if function_name == "binding_policy_management":
                operation = arguments.get("operation", "")

                if operation == "quick_create":
                    resources = arguments.get("resources")

                    if not resources or resources in ([], "", None):
                        validation_errors.append(
                            f"Step {i+1} ({function_name}): 'resources' parameter is REQUIRED for quick_create operation. "
                            f"Example: ['apps/deployments', 'core/services']"
                        )

                    # Validate and fix clusterSelectors format
                    cluster_selectors = arguments.get("cluster_selectors")

                    if cluster_selectors:
                        # Check if clusterSelectors has wrong format (missing matchLabels)
                        fixed_selectors = []
                        needs_fix = False
                        for selector in cluster_selectors:
                            # Handle MapComposite objects
                            if "MapComposite" in str(type(selector)):
                                try:
                                    # Convert MapComposite to dict recursively
                                    def convert_mapcomposite(obj):
                                        if "MapComposite" in str(type(obj)):
                                            if hasattr(obj, "items"):
                                                result = {}
                                                for k, v in obj.items():
                                                    result[k] = convert_mapcomposite(v)
                                                return result
                                            else:
                                                return str(obj)
                                        elif "RepeatedComposite" in str(type(obj)):
                                            if hasattr(obj, "__iter__"):
                                                return [
                                                    convert_mapcomposite(item)
                                                    for item in obj
                                                ]
                                            else:
                                                return str(obj)
                                        else:
                                            return obj

                                    selector_dict = convert_mapcomposite(selector)

                                    # Check if it already has proper structure (matchLabels or matchExpressions)
                                    if (
                                        "matchLabels" in selector_dict
                                        or "matchExpressions" in selector_dict
                                    ):
                                        # Use the converted dict as-is since it's already in correct format
                                        fixed_selectors.append(selector_dict)
                                        # Still need to update the plan to replace MapComposite with dict
                                        needs_fix = True
                                    else:
                                        # Wrap with matchLabels
                                        fixed_selector = {"matchLabels": selector_dict}
                                        fixed_selectors.append(fixed_selector)
                                        needs_fix = True
                                except Exception:
                                    fixed_selectors.append(selector)
                            # Handle string representations of dicts
                            elif isinstance(selector, str):
                                try:
                                    import json

                                    selector_dict = json.loads(selector)
                                    if isinstance(selector_dict, dict):
                                        # Check if selector already has proper structure (matchLabels or matchExpressions)
                                        if (
                                            "matchLabels" in selector_dict
                                            or "matchExpressions" in selector_dict
                                        ):
                                            # Already in correct format, use as-is
                                            fixed_selectors.append(selector_dict)
                                        else:
                                            # Wrong format - wrap with matchLabels
                                            fixed_selector = {
                                                "matchLabels": selector_dict
                                            }
                                            fixed_selectors.append(fixed_selector)
                                            needs_fix = True
                                    else:
                                        fixed_selectors.append(selector_dict)
                                except (ValueError, TypeError, json.JSONDecodeError):
                                    # If JSON parsing fails, treat as literal string
                                    fixed_selectors.append(selector)
                            elif isinstance(selector, dict):
                                # Check if selector already has proper structure (matchLabels or matchExpressions)
                                if (
                                    "matchLabels" in selector
                                    or "matchExpressions" in selector
                                ):
                                    # Already in correct format, use as-is
                                    fixed_selectors.append(selector)
                                else:
                                    # Wrong format - wrap with matchLabels
                                    fixed_selector = {"matchLabels": selector}
                                    fixed_selectors.append(fixed_selector)
                                    needs_fix = True
                            else:
                                fixed_selectors.append(selector)

                        if needs_fix:
                            # Auto-fix the plan
                            self.plan[i]["arguments"][
                                "cluster_selectors"
                            ] = fixed_selectors
                            self.console.print(
                                f"[dim]🔧 Auto-fixed clusterSelectors format in step {i+1}[/dim]"
                            )

            # Validate deploy_to has targeting information
            elif function_name == "deploy_to":
                target_clusters = arguments.get("target_clusters")
                cluster_labels = arguments.get("cluster_labels")
                context = arguments.get("context")

                if not target_clusters and not cluster_labels and not context:
                    validation_errors.append(
                        f"Step {i+1} ({function_name}): Must specify either target_clusters, cluster_labels, or context. "
                        f"For KubeStellar workflows, use target_clusters=['its1']"
                    )

        # Report validation errors
        if validation_errors:
            self.console.print("\n[bold red]⚠️  Plan Validation Errors:[/bold red]")
            for error in validation_errors:
                self.console.print(f"  ❌ {error}")
            self.console.print(
                "\n[yellow]Please regenerate the plan with the required parameters.[/yellow]"
            )
            return False

        return True

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
                formatted_value = self._format_value(value)
                # Escape the value to prevent Rich from interpreting brackets as markup tags
                self.console.print(f"     - {key}: {escape(formatted_value)}")
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

            # Update subsequent steps if fetch_manifest returned a new path
            if step["function_name"] == "fetch_manifest":
                try:
                    result_dict = json.loads(result)
                    if result_dict.get("status") == "success" and "path" in result_dict:
                        actual_path = result_dict["path"]
                        # Update filename in all subsequent deploy_to steps
                        for j in range(i + 1, len(self.plan)):
                            if self.plan[j]["function_name"] == "deploy_to":
                                if "filename" in self.plan[j]["arguments"]:
                                    # Update the filename to the actual path returned by fetch_manifest
                                    self.plan[j]["arguments"]["filename"] = actual_path
                except json.JSONDecodeError:
                    pass  # If we can't parse the result, continue without updating

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

        # Set up signal handler for Ctrl+C
        def signal_handler(sig, frame):
            self.console.print(
                "\n[yellow]⏹  Cancelling all operations... (Ctrl+C)[/yellow]"
            )
            self._cancel_all_tasks()

        # Store original signal handler
        original_sigint_handler = signal.signal(signal.SIGINT, signal_handler)

        # ASCII art for KubeStellar with proper formatting
        self.console.print()
        self.console.print(
            "[cyan]╭─────────────────────────────────────────────────────────────────────────────────────────────╮[/cyan]"
        )
        self.console.print(
            "[cyan]│[/cyan]                                                                                             [cyan]│[/cyan]"
        )
        self.console.print(
            "[cyan]│[/cyan]  [bold cyan]██╗  ██╗██╗   ██╗██████╗ ███████╗███████╗████████╗███████╗██╗     ██╗      █████╗ ██████╗[/bold cyan]  [cyan]│[/cyan]"
        )
        self.console.print(
            "[cyan]│[/cyan]  [bold cyan]██║ ██╔╝██║   ██║██╔══██╗██╔════╝██╔════╝╚══██╔══╝██╔════╝██║     ██║     ██╔══██╗██╔══██╗[/bold cyan] [cyan]│[/cyan]"
        )
        self.console.print(
            "[cyan]│[/cyan]  [bold cyan]█████╔╝ ██║   ██║██████╔╝█████╗  ███████╗   ██║   █████╗  ██║     ██║     ███████║██████╔╝[/bold cyan] [cyan]│[/cyan]"
        )
        self.console.print(
            "[cyan]│[/cyan]  [bold cyan]██╔═██╗ ██║   ██║██╔══██╗██╔══╝  ╚════██║   ██║   ██╔══╝  ██║     ██║     ██╔══██║██╔══██╗[/bold cyan] [cyan]│[/cyan]"
        )
        self.console.print(
            "[cyan]│[/cyan]  [bold cyan]██║  ██╗╚██████╔╝██████╔╝███████╗███████║   ██║   ███████╗███████╗███████╗██║  ██║██║  ██║[/bold cyan] [cyan]│[/cyan]"
        )
        self.console.print(
            "[cyan]│[/cyan]  [bold cyan]╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚══════╝   ╚═╝   ╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝[/bold cyan] [cyan]│[/cyan]"
        )
        self.console.print(
            "[cyan]│[/cyan]                                                                                             [cyan]│[/cyan]"
        )
        self.console.print(
            "[cyan]│[/cyan]                       [dim]🌟 Multi-Cluster Kubernetes Management Agent 🌟[/dim]                       [cyan]│[/cyan]"
        )
        self.console.print(
            "[cyan]╰─────────────────────────────────────────────────────────────────────────────────────────────╯[/cyan]"
        )
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
        try:
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
        finally:
            # Restore original signal handler
            signal.signal(signal.SIGINT, original_sigint_handler)

            # Cancel any remaining tasks
            self._cancel_all_tasks()

        if sys.stdin and sys.stdin.isatty():
            import termios

            termios.tcsetattr(
                sys.stdin.fileno(), termios.TCSADRAIN, self._old_tty_settings
            )
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
            prompt = f"""Please summarize the following JSON output from the `{function_name}` tool.
Focus on the most important information for the user, such as success or failure, names of created resources, or key data points.
Keep the summary concise and easy to read.

Tool Output:
```json
{result}
```"""
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
