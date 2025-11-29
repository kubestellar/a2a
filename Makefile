# kubestellar-a2a Makefile (repo root)
VENV := .venv
PY ?= python3
USE_UV ?= 1
UV ?= uv

PIP := $(VENV)/bin/pip
PYTHON := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff
BLACK := $(VENV)/bin/black
MYPY := $(VENV)/bin/mypy
BANDIT := $(VENV)/bin/bandit
SAFETY := $(VENV)/bin/safety
PYINSTALLER := $(VENV)/bin/pyinstaller

BIN_NAME := kubectl-a2a
DIST_DIR := dist
PKG_DIR := $(DIST_DIR)/pkg

OS := $(shell uname -s)
UNAME_M := $(shell uname -m)
# Map architectures
ifeq ($(UNAME_M),x86_64)
  ARCH := amd64
else ifeq ($(UNAME_M),aarch64)
  ARCH := arm64
else ifeq ($(UNAME_M),arm64)
  ARCH := arm64
else
  ARCH := amd64
endif

ifeq ($(OS),Linux)
  PLAT_TAG := linux-$(ARCH)
  BIN_FILE := $(DIST_DIR)/$(BIN_NAME)
else ifeq ($(OS),Darwin)
  PLAT_TAG := darwin-$(ARCH)
  BIN_FILE := $(DIST_DIR)/$(BIN_NAME)
else
  PLAT_TAG := windows-$(ARCH)
  BIN_FILE := $(DIST_DIR)/$(BIN_NAME).exe
endif

.DEFAULT_GOAL := help
.PHONY: help venv install dev lint format typecheck test security build-plugin dist-plugin dist-linux dist-darwin dist-windows dist-all sha256 clean

help:
	@echo "Targets:"
	@echo "  venv          Create virtualenv"
	@echo "  install       Install package (editable)"
	@echo "  dev           Install dev dependencies"
	@echo "  lint          Ruff lint"
	@echo "  format        Black format"
	@echo "  typecheck     Mypy type checks"
	@echo "  test          Pytest + coverage"
	@echo "  security      Bandit + Safety"
	@echo "  build-plugin  Build $(BIN_NAME) into dist/"
	@echo "  dist-plugin   Tar current OS binary to $(PKG_DIR)/$(BIN_NAME)-$(PLAT_TAG).tar.gz"
	@echo "  dist-linux    Tar Linux binary to $(PKG_DIR)"
	@echo "  dist-darwin   Tar macOS binary to $(PKG_DIR)"
	@echo "  dist-windows  Tar Windows binary to $(PKG_DIR)"
	@echo "  dist-all      Run all dist-* tar targets"
	@echo "  sha256        Print SHA256 for tarballs in $(PKG_DIR)"
	@echo "  clean         Remove build/dist/spec and caches"

venv:
	$(PY) -m venv $(VENV)
	. $(VENV)/bin/activate && $(PIP) install --upgrade pip

install: venv
ifeq ($(USE_UV),1)
	@if command -v $(UV) >/dev/null 2>&1; then \
		$(UV) pip install --python $(VENV)/bin/python -e . ; \
	else \
		echo "uv not found, falling back to pip" ; \
		. $(VENV)/bin/activate && $(PIP) install -e . ; \
	fi
else
	. $(VENV)/bin/activate && $(PIP) install -e .
endif

dev: install
ifeq ($(USE_UV),1)
	@if command -v $(UV) >/dev/null 2>&1; then \
		$(UV) pip install --python $(VENV)/bin/python -e ".[dev]" ; \
	else \
		echo "uv not found, falling back to pip" ; \
		. $(VENV)/bin/activate && $(PIP) install -e ".[dev]" ; \
	fi
else
	. $(VENV)/bin/activate && $(PIP) install -e ".[dev]"
endif

lint: dev
	$(RUFF) check .

format: dev
	$(BLACK) .

typecheck: dev
	$(MYPY) src

test: dev
	$(PYTEST) -q --cov=src --cov-report=term-missing

security: dev
	$(BANDIT) -r src tests || true
	$(SAFETY) check --full-report || true

# Build kubectl-a2a into dist/
build-plugin: dev
	@which $(PYINSTALLER) >/dev/null 2>&1 || (. $(VENV)/bin/activate && $(PIP) install pyinstaller)
	$(PYINSTALLER) --onefile --name $(BIN_NAME) --distpath $(DIST_DIR) --workpath build packaging/entry_kubectl_a2a.py

# Create tarball for current OS binary
dist-plugin: build-plugin
	mkdir -p $(PKG_DIR)
	[ -f "$(BIN_FILE)" ] || (echo "Binary not found: $(BIN_FILE)"; exit 1)
	cd $(DIST_DIR) && tar -czf pkg/$(BIN_NAME)-$(PLAT_TAG).tar.gz $(notdir $(BIN_FILE))
	@echo "Created: $(PKG_DIR)/$(BIN_NAME)-$(PLAT_TAG).tar.gz"

# Platform-specific tarballs (assumes binaries exist in dist/)
dist-linux:
	mkdir -p $(PKG_DIR)
	[ -f "dist/$(BIN_NAME)" ] || (echo "Missing Linux binary: dist/$(BIN_NAME)"; exit 1)
	cd dist && tar -czf pkg/$(BIN_NAME)-linux-$(ARCH).tar.gz $(BIN_NAME)

dist-darwin:
	mkdir -p $(PKG_DIR)
	[ -f "dist/$(BIN_NAME)" ] || (echo "Missing Darwin binary: dist/$(BIN_NAME)"; exit 1)
	cd dist && tar -czf pkg/$(BIN_NAME)-darwin-$(ARCH).tar.gz $(BIN_NAME)

dist-windows:
	mkdir -p $(PKG_DIR)
	[ -f "dist/$(BIN_NAME).exe" ] || (echo "Missing Windows binary: dist/$(BIN_NAME).exe"; exit 1)
	cd dist && tar -czf pkg/$(BIN_NAME)-windows-$(ARCH).tar.gz $(BIN_NAME).exe

dist-all: dist-linux dist-darwin dist-windows

sha256:
	@echo "SHA256 checksums for tarballs in $(PKG_DIR):"
	@if command -v sha256sum >/dev/null 2>&1; then \
	  sha256sum $(PKG_DIR)/*.tar.gz || true; \
	else \
	  shasum -a 256 $(PKG_DIR)/*.tar.gz || true; \
	fi

clean:
	rm -rf build dist *.spec
	rm -rf .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
