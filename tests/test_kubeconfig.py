"""Tests for kubeconfig function."""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.shared.functions.kubeconfig import KubeconfigFunction


@pytest.fixture
def kubeconfig_function():
    """Create a KubeconfigFunction instance."""
    return KubeconfigFunction()


@pytest.fixture
def sample_kubeconfig():
    """Create a sample kubeconfig for testing."""
    return {
        "apiVersion": "v1",
        "kind": "Config",
        "current-context": "test-context",
        "contexts": [
            {
                "name": "test-context",
                "context": {
                    "cluster": "test-cluster",
                    "user": "test-user",
                    "namespace": "default",
                },
            },
            {
                "name": "prod-context",
                "context": {
                    "cluster": "prod-cluster",
                    "user": "prod-user",
                    "namespace": "production",
                },
            },
        ],
        "clusters": [
            {
                "name": "test-cluster",
                "cluster": {
                    "server": "https://test.example.com:6443",
                    "insecure-skip-tls-verify": False,
                },
            },
            {
                "name": "prod-cluster",
                "cluster": {
                    "server": "https://prod.example.com:6443",
                    "insecure-skip-tls-verify": True,
                },
            },
        ],
        "users": [
            {
                "name": "test-user",
                "user": {
                    "client-certificate": "/path/to/cert",
                    "client-key": "/path/to/key",
                },
            },
            {"name": "prod-user", "user": {"token": "test-token"}},
        ],
    }


@pytest.mark.asyncio
async def test_kubeconfig_function_metadata(kubeconfig_function):
    """Test function metadata."""
    assert kubeconfig_function.name == "get_kubeconfig"
    assert "kubeconfig" in kubeconfig_function.description.lower()

    schema = kubeconfig_function.get_schema()
    assert schema["type"] == "object"
    assert "kubeconfig_path" in schema["properties"]
    assert "context" in schema["properties"]
    assert "detail_level" in schema["properties"]


@pytest.mark.asyncio
async def test_kubeconfig_nonexistent_file(kubeconfig_function):
    """Test with non-existent kubeconfig file."""
    result = await kubeconfig_function.execute(kubeconfig_path="/nonexistent/path")
    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_kubeconfig_summary(kubeconfig_function, sample_kubeconfig):
    """Test getting kubeconfig summary."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_kubeconfig, f)
        temp_path = f.name

    try:
        result = await kubeconfig_function.execute(kubeconfig_path=temp_path)
        assert result["current_context"] == "test-context"
        assert result["total_contexts"] == 2
        assert "test-context" in result["contexts"]
        assert "prod-context" in result["contexts"]
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_kubeconfig_specific_context(kubeconfig_function, sample_kubeconfig):
    """Test getting specific context details."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_kubeconfig, f)
        temp_path = f.name

    try:
        result = await kubeconfig_function.execute(
            kubeconfig_path=temp_path, context="prod-context"
        )
        assert "selected_context" in result
        assert result["selected_context"]["name"] == "prod-context"
        assert result["selected_context"]["cluster"] == "prod-cluster"
        assert result["selected_context"]["namespace"] == "production"
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_kubeconfig_invalid_context(kubeconfig_function, sample_kubeconfig):
    """Test with invalid context name."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_kubeconfig, f)
        temp_path = f.name

    try:
        result = await kubeconfig_function.execute(
            kubeconfig_path=temp_path, context="nonexistent-context"
        )
        assert "error" in result
        assert "not found" in result["error"]
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_kubeconfig_full_details(kubeconfig_function, sample_kubeconfig):
    """Test getting full kubeconfig details."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_kubeconfig, f)
        temp_path = f.name

    try:
        result = await kubeconfig_function.execute(
            kubeconfig_path=temp_path, detail_level="full"
        )
        assert "clusters" in result
        assert len(result["clusters"]) == 2
        assert "users" in result
        assert len(result["users"]) == 2

        # Check cluster details
        test_cluster = next(
            c for c in result["clusters"] if c["name"] == "test-cluster"
        )
        assert test_cluster["server"] == "https://test.example.com:6443"

        # Check user details (should be sanitized)
        test_user = next(u for u in result["users"] if u["name"] == "test-user")
        assert "certificate" in test_user["auth_type"]

        prod_user = next(u for u in result["users"] if u["name"] == "prod-user")
        assert "token" in prod_user["auth_type"]
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_kubeconfig_contexts_detail(kubeconfig_function, sample_kubeconfig):
    """Test getting contexts detail level."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_kubeconfig, f)
        temp_path = f.name

    try:
        result = await kubeconfig_function.execute(
            kubeconfig_path=temp_path, detail_level="contexts"
        )
        assert "context_details" in result
        assert len(result["context_details"]) == 2

        test_context = next(
            c for c in result["context_details"] if c["name"] == "test-context"
        )
        assert test_context["cluster"] == "test-cluster"
        assert test_context["user"] == "test-user"
        assert test_context["namespace"] == "default"
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_kubeconfig_invalid_yaml(kubeconfig_function):
    """Test with invalid YAML file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("invalid: yaml: content: {{{")
        temp_path = f.name

    try:
        result = await kubeconfig_function.execute(kubeconfig_path=temp_path)
        assert "error" in result
        assert "Failed to parse" in result["error"]
    finally:
        Path(temp_path).unlink()
