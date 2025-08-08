"""Tests for KubeStellar CLI."""

import json

import pytest
from click.testing import CliRunner

from src.a2a.cli import cli


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


def test_cli_help(runner):
    """Test CLI help command."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "KubeStellar A2A Agent" in result.output


def test_list_functions(runner):
    """Test listing available functions."""
    result = runner.invoke(cli, ["list-functions"])
    assert result.exit_code == 0
    assert "Available A2A Functions:" in result.output
    assert "get_kubeconfig" in result.output


def test_describe_function(runner):
    """Test describing a specific function."""
    result = runner.invoke(cli, ["describe", "get_kubeconfig"])
    assert result.exit_code == 0
    assert "Function: get_kubeconfig" in result.output
    assert "Schema:" in result.output
    assert "kubeconfig_path" in result.output


def test_describe_nonexistent_function(runner):
    """Test describing a function that doesn't exist."""
    result = runner.invoke(cli, ["describe", "nonexistent_function"])
    assert result.exit_code == 0
    assert "Error: Function 'nonexistent_function' not found." in result.output


def test_execute_function_with_params(runner):
    """Test executing a function with parameters."""
    # This test will work even without a real kubeconfig
    result = runner.invoke(
        cli,
        ["execute", "get_kubeconfig", "--param", "kubeconfig_path=/nonexistent/path"],
    )
    assert result.exit_code == 0
    # Should get an error response but in valid JSON format
    output = json.loads(result.output)
    assert "error" in output or "kubeconfig_path" in output


def test_execute_function_with_json_params(runner):
    """Test executing a function with JSON parameters."""
    params = json.dumps(
        {"kubeconfig_path": "/nonexistent/path", "detail_level": "full"}
    )
    result = runner.invoke(cli, ["execute", "get_kubeconfig", "--params", params])
    assert result.exit_code == 0
    output = json.loads(result.output)
    assert isinstance(output, dict)


def test_execute_nonexistent_function(runner):
    """Test executing a function that doesn't exist."""
    result = runner.invoke(cli, ["execute", "nonexistent_function"])
    assert result.exit_code == 0
    assert "Error: Function 'nonexistent_function' not found." in result.output
    assert "Use 'list-functions' to see available functions." in result.output


def test_execute_invalid_param_format(runner):
    """Test executing with invalid parameter format."""
    result = runner.invoke(
        cli, ["execute", "get_kubeconfig", "--param", "invalid_format"]
    )
    assert result.exit_code == 0
    assert "Error: Invalid parameter format" in result.output
    assert "Use key=value" in result.output


def test_execute_invalid_json_params(runner):
    """Test executing with invalid JSON parameters."""
    result = runner.invoke(
        cli, ["execute", "get_kubeconfig", "--params", "{invalid json}"]
    )
    assert result.exit_code == 0
    assert "Error: Invalid JSON parameters" in result.output
