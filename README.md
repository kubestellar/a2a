# KubeStellar A2A

📚 **[View Full Documentation](https://kubestellar.github.io/a2a/)**

```
╭─────────────────────────────────────────────────────────────────────────────────────────────╮
│  ██╗  ██╗██╗   ██╗██████╗ ███████╗███████╗████████╗███████╗██╗     ██╗      █████╗ ██████╗  │
│  ██║ ██╔╝██║   ██║██╔══██╗██╔════╝██╔════╝╚══██╔══╝██╔════╝██║     ██║     ██╔══██╗██╔══██╗ │
│  █████╔╝ ██║   ██║██████╔╝█████╗  ███████╗   ██║   █████╗  ██║     ██║     ███████║██████╔╝ │
│  ██╔═██╗ ██║   ██║██╔══██╗██╔══╝  ╚════██║   ██║   ██╔══╝  ██║     ██║     ██╔══██║██╔══██╗ │
│  ██║  ██╗╚██████╔╝██████╔╝███████╗███████║   ██║   ███████╗███████╗███████╗██║  ██║██║  ██║ │
│  ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚══════╝   ╚═╝   ╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ │
│                       Multi-Cluster Kubernetes Management Agent                             │
╰─────────────────────────────────────────────────────────────────────────────────────────────╯
```


https://github.com/user-attachments/assets/fd5746f9-6620-4aeb-8150-dd9bf9eab694


## CLI Setup (uv)

```bash
# Enable virtual environment
uv venv

# Install with uv
uv pip install -e ".[dev]"

# Run commands
uv run kubestellar --help
uv run kubestellar list-functions
uv run kubestellar execute <function_name>
uv run kubestellar agent  # Start interactive AI agent
```

## AI Provider Configuration

The agent supports multiple AI providers:

### Available Providers
- **OpenAI** (GPT-4, GPT-4o, etc.)
- **Google Gemini** (gemini-1.5-flash, gemini-1.5-pro, etc.)

### Setting Up API Keys

```bash
# Set OpenAI API key
uv run kubestellar config set-key openai YOUR_OPENAI_API_KEY

# Set Gemini API key  
uv run kubestellar config set-key gemini YOUR_GEMINI_API_KEY

# Set default provider
uv run kubestellar config set-default gemini

# List configured providers
uv run kubestellar config list-keys

# Show current configuration
uv run kubestellar config show
```

### Using Different Providers

```bash
# Use default provider
uv run kubestellar agent

# Use specific provider
uv run kubestellar agent --provider gemini
uv run kubestellar agent --provider openai
```

## MCP Server Setup

Add to MCP server (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "kubestellar": {
      "command": "uv",
      "args": ["run", "kubestellar-mcp"],
      "cwd": "/path/to/a2a"
    }
  }
}
```

## Documentation

📖 **Complete Documentation:** https://kubestellar.github.io/a2a/

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [MCP SDK](https://github.com/anthropics/mcp-sdk)
- Inspired by the KubeStellar project for multi-cluster Kubernetes management
- Thanks to all contributors and the open-source community

---

Made with ❤️ by the KubeStellar community
