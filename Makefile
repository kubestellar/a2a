UV ?= uv

.DEFAULT_GOAL := help
.PHONY: help install dev lint test clean plugin-install plugin-uninstall plugin-upgrade

help:
	@echo "Targets:"
	@echo "  install          Install project dependencies (uv)"
	@echo "  dev              Install dev dependencies (uv)"
	@echo "  lint             Run ruff linting"
	@echo "  test             Run tests with pytest"
	@echo "  clean            Clean caches"
	@echo "  plugin-install   Install kubectl-a2a via uv tool"
	@echo "  plugin-uninstall Uninstall kubectl-a2a from uv tool"
	@echo "  plugin-upgrade   Upgrade kubectl-a2a via uv tool"

install:
	@command -v $(UV) >/dev/null 2>&1 || (echo "uv is required. Install from https://astral.sh/uv" && exit 1)
	$(UV) sync

dev:
	$(UV) sync --group dev

lint:
	$(UV) run ruff check src/ tests/

test:
	$(UV) run pytest -q --cov=src --cov-report=term-missing

clean:
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

plugin-install:
	$(UV) tool install .
	@echo "Run: kubectl a2a --help"

plugin-uninstall:
	$(UV) tool uninstall kubestellar || true
	$(UV) tool uninstall kubectl-a2a || true

plugin-upgrade:
	$(UV) tool upgrade kubestellar || true
