# KubeStellar A2A Agent

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
# Install with uv
uv pip install -e ".[dev]"

# Run commands
uv run kubestellar --help
uv run kubestellar list-functions
uv run kubestellar execute <function_name>
uv run kubestellar agent  # Start interactive AI agent
```

## MCP Server Setup

Add to Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

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

## Testing & Development

### 🧪 Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src

# Run specific test file
uv run pytest tests/test_kubestellar_setup.py

# Run with verbose output
uv run pytest -v
```

**Test Status: ✅ All 130+ tests passing**

- CLI tests: 9 tests passing
- Base function tests: 8 tests passing  
- Kubeconfig function tests: 8 tests passing
- **KubeStellar setup tests: 21 tests passing** ✨ **NEW**
- Helm deployment tests: 35 tests passing
- KubeStellar management tests: Various integration tests
- GVRC discovery tests: Resource discovery validation
- Namespace utilities tests: Multi-namespace functionality

### 🔧 Code Quality & Linting

This project uses several tools to maintain code quality and consistency. All checks are automatically run in CI, but you can run them locally during development.

#### Individual Tools

```bash
# Format code with Black
uv run black src/ tests/

# Check formatting (without changing files)
uv run black --check src/ tests/

# Lint code with Ruff (fast Python linter)
uv run ruff check src/ tests/

# Auto-fix linting issues
uv run ruff check src/ tests/ --fix

# Sort imports with isort
uv run isort src/ tests/

# Check import sorting (without changing files)  
uv run isort --check-only src/ tests/

# Type check with mypy
uv run mypy src/

# Security scan with bandit
uv run bandit -r src/

# Check for dependency vulnerabilities
uv run safety check
```

#### Combined Quality Checks

```bash
# Run all formatting and linting checks
uv run black --check src/ tests/ && \
uv run isort --check-only src/ tests/ && \
uv run ruff check src/ tests/ && \
uv run mypy src/

# Fix all auto-fixable issues
uv run black src/ tests/ && \
uv run isort src/ tests/ && \
uv run ruff check src/ tests/ --fix

# Run complete quality check (like CI)
uv run pytest tests/ -v && \
uv run black --check src/ tests/ && \
uv run isort --check-only src/ tests/ && \
uv run ruff check src/ tests/ && \
uv run mypy src/ --ignore-missing-imports && \
uv run bandit -r src/ -ll
```

#### Pre-commit Workflow

Before committing code, run:

```bash
# 1. Format and fix issues
uv run black src/ tests/
uv run isort src/ tests/  
uv run ruff check src/ tests/ --fix

# 2. Run tests
uv run pytest tests/ -v

# 3. Verify all checks pass
uv run black --check src/ tests/
uv run isort --check-only src/ tests/
uv run ruff check src/ tests/
```

### 🚀 New KubeStellar Setup Function

Test the complete KubeStellar v0.28.0 setup automation:

```bash
# Verify prerequisites
uv run kubestellar execute kubestellar_setup -p '{"operation": "verify_prerequisites"}'

# Complete setup (follows official docs.kubestellar.io)
uv run kubestellar execute kubestellar_setup -p '{
  "operation": "full_setup",
  "platform": "kind",
  "kubestellar_version": "v0.28.0"
}'

# Quick automated setup
uv run kubestellar execute kubestellar_setup -p '{
  "operation": "full_setup",
  "automated_script": true,
  "platform": "kind"
}'
```

## Documentation

📖 **Complete Documentation:** https://kubestellar.github.io/a2a/

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [MCP SDK](https://github.com/anthropics/mcp-sdk)
- Inspired by the KubeStellar project for multi-cluster Kubernetes management
- Thanks to all contributors and the open-source community

---

Made with ❤️ by the KubeStellar community
