"""A2A Agent CLI implementation."""

import asyncio
import json
from typing import Any, Dict, Optional

import click

from src.agent import AgentChat
from src.llm_providers.config import get_config_manager
from src.llm_providers.registry import list_providers
from src.shared.base_functions import async_to_sync, function_registry
from src.shared.functions import initialize_functions


def _init_ctx(ctx: click.Context, quiet: bool, verbose: bool) -> None:
    ctx.ensure_object(dict)
    ctx.obj["quiet"] = quiet
    ctx.obj["verbose"] = verbose


def _echo(ctx: click.Context, message: str, *, err: bool = False) -> None:
    if not ctx.obj.get("quiet", False):
        click.echo(message, err=err)


def _echo_verbose(ctx: click.Context, message: str) -> None:
    if ctx.obj.get("verbose", False):
        click.echo(message)


def _is_quiet(ctx: click.Context) -> bool:
    return ctx.obj.get("quiet", False)


def _is_verbose(ctx: click.Context) -> bool:
    return ctx.obj.get("verbose", False)


@click.group(
    help="KubeStellar Agent - Interact with automation functions and agent mode."
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress informational output; only critical results and errors are shown.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging for command execution details.",
)
@click.pass_context
def cli(ctx: click.Context, quiet: bool, verbose: bool) -> None:
    """Root command for the KubeStellar A2A CLI."""
    if quiet and verbose:
        raise click.UsageError("Cannot use --quiet and --verbose together.")

    # Initialize functions when CLI starts
    initialize_functions()
    _init_ctx(ctx, quiet, verbose)


@cli.command(help="List available functions and their parameters.")
@click.pass_context
def list_functions(ctx: click.Context) -> None:
    """Display the function catalog with parameter descriptions."""
    functions = function_registry.list_all()
    if not functions:
        _echo(ctx, "No functions registered.")
        return

    if _is_quiet(ctx):
        for func in functions:
            click.echo(func.name)
        return

    _echo(ctx, "Available functions:")
    for func in functions:
        _echo(ctx, f"\n- {func.name}")
        _echo(ctx, f"  Description: {func.description}")
        schema = func.get_schema()
        if schema.get("properties"):
            _echo(ctx, "  Parameters:")
            for param, details in schema["properties"].items():
                required = param in schema.get("required", [])
                req_str = " (required)" if required else " (optional)"
                _echo(ctx, f"    - {param}: {details.get('type', 'any')}{req_str}")
                if "description" in details:
                    _echo(ctx, f"      {details['description']}")


@cli.command(help="Execute a function with either JSON input or key=value pairs.")
@click.argument("function_name")
@click.option(
    "--params",
    "-p",
    help="JSON body, e.g. -p '{\"chart\":\"nginx\",\"version\":\"1.2.0\"}'",
)
@click.option(
    "--param",
    "-P",
    multiple=True,
    help="Add key=value parameters (repeat for multiple values).",
)
@click.pass_context
def execute(
    ctx: click.Context,
    function_name: str,
    params: Optional[str],
    param: tuple[str, ...],
) -> None:
    """Invoke an automation function."""
    function = function_registry.get(function_name)
    if not function:
        click.echo(f"Error: Function '{function_name}' not found.", err=True)
        click.echo("Use 'list-functions' to see available functions.", err=True)
        return

    # Parse parameters
    kwargs: Dict[str, Any] = {}

    if _is_verbose(ctx):
        _echo_verbose(
            ctx,
            f"Raw parameters received: params={params!r}, repeats={param!r}",
        )

    if params and param:
        click.echo(
            "Error: Provide parameters either via --params JSON or -P key=value, not both.",
            err=True,
        )
        return

    if params:
        try:
            kwargs = json.loads(params)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON parameters: {e}", err=True)
            return

    # Parse key=value pairs
    for p in param:
        if "=" not in p:
            click.echo(
                f"Error: Invalid parameter format '{p}'. Use key=value", err=True
            )
            return
        key, value = p.split("=", 1)
        # Try to parse as JSON, fallback to string
        try:
            kwargs[key] = json.loads(value)
        except json.JSONDecodeError:
            kwargs[key] = value

    if _is_verbose(ctx):
        _echo_verbose(ctx, f"Parsed parameters: {kwargs!r}")

    # Execute function
    try:
        function.validate_inputs(kwargs)

        if _is_verbose(ctx):
            _echo_verbose(ctx, "Inputs validated successfully.")

        # Convert async function to sync for CLI
        if asyncio.iscoroutinefunction(function.execute):
            result = async_to_sync(function.execute)(**kwargs)
        else:
            result = function.execute(**kwargs)

        if _is_verbose(ctx):
            _echo_verbose(ctx, f"Execution result: {result!r}")

        click.echo(json.dumps(result, indent=2))
    except ValueError as e:
        click.echo(f"Validation error: {e}", err=True)
    except Exception as e:
        click.echo(f"Error executing function: {e}", err=True)


@cli.command(help="Show the JSON schema and metadata for a function.")
@click.argument("function_name")
def describe(function_name: str) -> None:
    """Display detailed information about a function."""
    function = function_registry.get(function_name)
    if not function:
        click.echo(f"Error: Function '{function_name}' not found.", err=True)
        return

    click.echo(f"Function: {function.name}")
    click.echo(f"Description: {function.description}")
    click.echo("\nSchema:")
    click.echo(json.dumps(function.get_schema(), indent=2))


@cli.command(help="Launch the interactive agent for conversational control.")
@click.option(
    "--provider",
    "-p",
    help="Override the configured default provider (e.g. --provider openai)",
)
def agent(provider: Optional[str]) -> None:
    """Start interactive agent mode with LLM assistance."""
    try:
        chat = AgentChat(provider_name=provider)
        asyncio.run(chat.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.group(help="Manage stored API keys and preferred provider settings.")
def config() -> None:
    """Configuration commands."""


@config.command("set-key", help="Store an API key for the given provider.")
@click.argument("provider")
@click.argument("api_key")
def set_api_key(provider: str, api_key: str) -> None:
    """Persist an API key for a provider."""
    config_manager = get_config_manager()
    config_manager.set_api_key(provider, api_key)


@config.command("remove-key", help="Delete the stored API key for a provider.")
@click.argument("provider")
def remove_api_key(provider: str) -> None:
    """Remove a provider's stored API key."""
    config_manager = get_config_manager()
    config_manager.remove_api_key(provider)


@config.command("list-keys", help="List which providers have API keys configured.")
def list_api_keys() -> None:
    """Show providers with stored API keys (without revealing secrets)."""
    config_manager = get_config_manager()
    keys = config_manager.list_api_keys()

    if not keys:
        click.echo("No API keys configured.")
        return

    click.echo("Configured API keys:")
    for provider, has_key in keys.items():
        status = "✓" if has_key else "✗"
        click.echo(f"  {status} {provider}")


@config.command("set-default")
@click.argument("provider")
def set_default_provider(provider: str) -> None:
    """Set default LLM provider."""
    available = list_providers()
    if provider not in available:
        click.echo(f"Error: Unknown provider '{provider}'", err=True)
        click.echo(f"Available providers: {', '.join(available)}", err=True)
        return

    config_manager = get_config_manager()
    config_manager.set_default_provider(provider)


@config.command("show")
def show_config() -> None:
    """Show current configuration."""
    config_manager = get_config_manager()
    config = config_manager.load_config()

    click.echo("Current configuration:")
    click.echo(json.dumps(config, indent=2))


@cli.command("providers", help="List installed LLM providers and mark the default.")
def list_providers_cmd() -> None:
    """Display known LLM providers and highlight the default selection."""
    providers = list_providers()
    config_manager = get_config_manager()
    default_provider = config_manager.get_default_provider()
    click.echo("Available LLM providers:")
    for provider in providers:
        marker = " (default)" if provider == default_provider else ""
        click.echo(f"  - {provider}{marker}")


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
