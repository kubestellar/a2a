"""A2A Agent CLI implementation."""

import asyncio
import json
from typing import Any, Dict, Optional

import click

from ..llm_providers.config import get_config_manager
from ..llm_providers.registry import list_providers
from ..shared.base_functions import async_to_sync, function_registry
from ..shared.functions import initialize_functions
from .agent import AgentChat


@click.group()
@click.pass_context
def cli(ctx):
    """🌟 KubeStellar A2A Agent - AI-Powered Multi-Cluster Kubernetes Management
    
    Advanced agent-to-agent platform for intelligent Kubernetes operations:
    
    🚀 QUICK START:
      kubestellar execute kubestellar_setup -p '{"operation": "verify_prerequisites"}'
      kubestellar execute kubestellar_setup -p '{"operation": "full_setup", "platform": "kind"}'
    
    🤖 KEY FEATURES:
      • Complete KubeStellar v0.28.0 setup automation
      • Multi-cluster resource management and deployment  
      • AI-powered interactive agent with natural language queries
      • Comprehensive prerequisite verification and error handling
      • Integration with Claude Desktop via MCP server
    
    📊 CORE FUNCTIONS:
      • kubestellar_setup     - Automated KubeStellar environment setup
      • kubestellar_management - Advanced multi-cluster analysis
      • helm_deploy           - Helm charts with binding policies
      • multicluster_create   - Deploy across all clusters
      • multicluster_logs     - Aggregate logs from multiple clusters
    
    🔗 Learn more: https://kubestellar.github.io/a2a/
    """
    # Initialize functions when CLI starts
    initialize_functions()
    ctx.ensure_object(dict)


@cli.command()
def list_functions():
    """List all available A2A functions with setup highlights."""
    functions = function_registry.list_all()
    if not functions:
        click.echo("No functions registered.")
        return

    # Sort functions to show setup first
    sorted_functions = sorted(functions, key=lambda f: (
        0 if f.name == "kubestellar_setup" else
        1 if f.name == "kubestellar_management" else 2
    ))

    click.echo("🤖 Available A2A Functions:\n")
    
    for i, func in enumerate(sorted_functions):
        # Highlight setup function
        if func.name == "kubestellar_setup":
            click.echo(f"🌟 {func.name} (FEATURED)")
            click.echo(f"  📖 {func.description}")
        else:
            click.echo(f"- {func.name}")
            click.echo(f"  Description: {func.description}")
            
        schema = func.get_schema()
        if schema.get("properties"):
            click.echo("  Parameters:")
            param_count = len(schema["properties"])
            if param_count > 5:  # Show only key parameters for long lists
                key_params = list(schema["properties"].items())[:3]
                for param, details in key_params:
                    required = param in schema.get("required", [])
                    req_str = " (required)" if required else " (optional)"
                    click.echo(f"    - {param}: {details.get('type', 'any')}{req_str}")
                    if "description" in details:
                        click.echo(f"      {details['description']}")
                click.echo(f"    ... and {param_count - 3} more parameters")
            else:
                for param, details in schema["properties"].items():
                    required = param in schema.get("required", [])
                    req_str = " (required)" if required else " (optional)"
                    click.echo(f"    - {param}: {details.get('type', 'any')}{req_str}")
                    if "description" in details:
                        click.echo(f"      {details['description']}")
        
        if i < len(sorted_functions) - 1:
            click.echo("")
    
    click.echo("\n💡 Quick Start:")
    click.echo("   kubestellar describe kubestellar_setup")
    click.echo("   kubestellar execute kubestellar_setup -p '{\"operation\": \"verify_prerequisites\"}'")
    click.echo("\n🔗 Full documentation: https://kubestellar.github.io/a2a/")


@cli.command()
@click.argument("function_name")
@click.option("--params", "-p", help="JSON string of parameters")
@click.option("--param", "-P", multiple=True, help="Key=value parameter pairs")
def execute(function_name: str, params: Optional[str], param: tuple):
    """Execute a specific function."""
    function = function_registry.get(function_name)
    if not function:
        click.echo(f"Error: Function '{function_name}' not found.", err=True)
        click.echo("Use 'list-functions' to see available functions.", err=True)
        return

    # Parse parameters
    kwargs: Dict[str, Any] = {}

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

    # Execute function
    try:
        # Convert async function to sync for CLI
        if asyncio.iscoroutinefunction(function.execute):
            result = async_to_sync(function.execute)(**kwargs)
        else:
            result = function.execute(**kwargs)

        click.echo(json.dumps(result, indent=2))
    except Exception as e:
        click.echo(f"Error executing function: {e}", err=True)


@cli.command()
@click.argument("function_name")
def describe(function_name: str):
    """Get detailed information about a function."""
    function = function_registry.get(function_name)
    if not function:
        click.echo(f"Error: Function '{function_name}' not found.", err=True)
        return

    click.echo(f"Function: {function.name}")
    click.echo(f"Description: {function.description}")
    click.echo("\nSchema:")
    click.echo(json.dumps(function.get_schema(), indent=2))


@cli.command()
@click.option("--provider", "-p", help="LLM provider to use (default: from config)")
def agent(provider: Optional[str]):
    """Start interactive agent mode with LLM assistance."""
    try:
        chat = AgentChat(provider_name=provider)
        asyncio.run(chat.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.group()
def config():
    """Manage configuration and API keys."""
    pass


@config.command("set-key")
@click.argument("provider")
@click.argument("api_key")
def set_api_key(provider: str, api_key: str):
    """Set API key for a provider."""
    config_manager = get_config_manager()
    config_manager.set_api_key(provider, api_key)


@config.command("remove-key")
@click.argument("provider")
def remove_api_key(provider: str):
    """Remove API key for a provider."""
    config_manager = get_config_manager()
    config_manager.remove_api_key(provider)


@config.command("list-keys")
def list_api_keys():
    """List providers with stored API keys."""
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
def set_default_provider(provider: str):
    """Set default LLM provider."""
    available = list_providers()
    if provider not in available:
        click.echo(f"Error: Unknown provider '{provider}'", err=True)
        click.echo(f"Available providers: {', '.join(available)}", err=True)
        return

    config_manager = get_config_manager()
    config_manager.set_default_provider(provider)


@config.command("show")
def show_config():
    """Show current configuration."""
    config_manager = get_config_manager()
    config = config_manager.load_config()

    click.echo("Current configuration:")
    click.echo(json.dumps(config, indent=2))


@cli.command("providers")
def list_providers_cmd():
    """List available LLM providers."""
    providers = list_providers()
    click.echo("Available LLM providers:")
    for provider in providers:
        click.echo(f"  - {provider}")


def main():
    """Main entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
