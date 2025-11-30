# kubestellar-a2a Makefile (using uv CLI directly)
UV ?= uv
UV_CACHE_DIR ?= .uv-cache
export UV_CACHE_DIR

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
.PHONY: help install dev lint format typecheck test security build-plugin dist-plugin dist-linux dist-darwin dist-windows dist-all sha256 clean docker-build docker-run docker-shell docker-buildx

help:
	@echo "Targets (using uv CLI directly):"
	@echo "  install       Install package dependencies"
	@echo "  dev           Install dev dependencies"
	@echo "  lint          Run ruff linting"
	@echo "  format        Format code with black"
	@echo "  typecheck     Type check with mypy"
	@echo "  test          Run tests with pytest"
	@echo "  security      Security checks with bandit and safety"
	@echo "  build-plugin  Build $(BIN_NAME) binary"
	@echo "  dist-plugin   Package binary to tarball"
	@echo "  dist-linux    Package Linux binary"
	@echo "  dist-darwin   Package macOS binary"
	@echo "  dist-windows  Package Windows binary"
	@echo "  dist-all      Package all platforms"
	@echo "  sha256        Generate checksums"
	@echo "  clean         Clean build artifacts"
	@echo "  docker-build  Build Docker image"
	@echo "  docker-run    Run Docker image"
	@echo "  docker-shell  Shell into Docker image"
	@echo "  docker-buildx Multi-arch Docker build"

install:
	@command -v $(UV) >/dev/null 2>&1 || (echo "uv is required. Install from https://astral.sh/uv" && exit 1)
	$(UV) sync --locked

dev:
	$(UV) sync --locked --group dev

lint: dev
	$(UV) run ruff check .

format: dev
	$(UV) run black .

typecheck: dev
	$(UV) run mypy src

test: dev
	$(UV) run pytest -q --cov=src --cov-report=term-missing

security: dev
	$(UV) run bandit -r src tests || true
	$(UV) run safety check --full-report || true

# Build kubectl-a2a binary
build-plugin: dev
	$(UV) pip install pyinstaller
	$(UV) run pyinstaller --onefile --name $(BIN_NAME) --distpath $(DIST_DIR) --workpath build packaging/entry_kubectl_a2a.py

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
	  sha256sum $(PKG_DIR)/*.tar.gz 2>/dev/null || echo "No tarballs found"; \
	else \
	  shasum -a 256 $(PKG_DIR)/*.tar.gz 2>/dev/null || echo "No tarballs found"; \
	fi

clean:
	rm -rf build dist *.spec
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Docker helpers
DOCKER_IMAGE ?= kubestellar/a2a
DOCKER_TAG ?= uv
ARGS ?= --help

docker-build:
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

docker-run:
	docker run --rm $(DOCKER_IMAGE):$(DOCKER_TAG) $(ARGS)

docker-shell:
	docker run --rm -it --entrypoint sh $(DOCKER_IMAGE):$(DOCKER_TAG)

docker-buildx:
	docker buildx build --platform linux/amd64,linux/arm64 -t $(DOCKER_IMAGE):$(DOCKER_TAG) .
