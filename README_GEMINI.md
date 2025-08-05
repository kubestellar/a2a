# KubeStellar Agent with Gemini Integration

This project extends the KubeStellar Agent with Google Gemini AI integration, providing an interactive chat interface similar to Claude Code.

## Features

- **Multi-Provider Architecture**: Supports multiple LLM providers (currently Gemini, with easy extension for Claude, OpenAI, etc.)
- **Interactive Agent Mode**: Claude Code-like interface with rich formatting
- **Token Usage Tracking**: Display token usage after each response
- **Thinking/Reasoning Support**: For models that support it (e.g., gemini-2.0-flash-thinking-exp-1219)
- **Environment-based Configuration**: API keys stored in `.env` file
- **KubeStellar Function Integration**: All KubeStellar functions available through the agent

## Installation

1. Create a virtual environment:
```bash
uv venv
source .venv/bin/activate
```

2. Install the package:
```bash
uv pip install -e .
```

3. Set up your API key:
```bash
cp .env.example .env
# Edit .env and add your Gemini API key
```

## Usage

### Interactive Agent Mode
```bash
kubestellar agent
```

This launches the interactive chat interface where you can:
- Ask questions about KubeStellar
- Execute KubeStellar functions
- Get help with multi-cluster Kubernetes management

### Configuration Commands

```bash
# Set API key (alternative to .env)
kubestellar config set-key gemini YOUR_API_KEY

# Set default provider
kubestellar config set-default gemini

# List configured providers
kubestellar config list-keys

# Show current configuration
kubestellar config show
```

### Direct Function Execution

```bash
# List available functions
kubestellar list-functions

# Execute a specific function
kubestellar execute <function-name> --params '{"param": "value"}'
```

## Available Gemini Models

- `gemini-1.5-flash` (default)
- `gemini-1.5-flash-8b`
- `gemini-1.5-pro`
- `gemini-1.0-pro`
- `gemini-2.0-flash-thinking-exp-1219` (with thinking support)
- `gemini-2.0-flash-exp`

## Environment Variables

- `GEMINI_API_KEY`: Your Gemini API key
- `DEFAULT_LLM_PROVIDER`: Default provider (gemini)
- `GEMINI_MODEL`: Default Gemini model
- `SHOW_THINKING`: Show thinking blocks (true/false)
- `SHOW_TOKEN_USAGE`: Show token usage (true/false)
- `COLOR_OUTPUT`: Enable colored output (true/false)

## Adding New Providers

To add a new LLM provider:

1. Create a new file in `src/llm_providers/` (e.g., `claude.py`)
2. Implement the `BaseLLMProvider` interface
3. Register the provider in the registry
4. Add configuration in `.env.example`

Example:
```python
from .base import BaseLLMProvider
from .registry import register_provider

class ClaudeProvider(BaseLLMProvider):
    # Implement required methods
    pass

register_provider("claude", ClaudeProvider)
```

## Architecture

```
src/
├── a2a/
│   ├── agent.py        # Interactive chat interface
│   └── cli.py          # CLI commands
├── llm_providers/
│   ├── base.py         # Base provider interface
│   ├── gemini.py       # Gemini implementation
│   ├── config.py       # Configuration management
│   └── registry.py     # Provider registry
└── shared/
    └── functions/      # KubeStellar functions
```

The system uses a provider abstraction that makes it easy to add new LLM providers while maintaining a consistent interface.