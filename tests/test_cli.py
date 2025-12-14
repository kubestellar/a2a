"""Tests for KubeStellar CLI."""

import json

import pytest
from click.testing import CliRunner

from src.cli import cli


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


def _load_json_from_output(text: str) -> dict:
    """Extract the JSON payload from CLI output that may include log lines."""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip().startswith("{"):
            return json.loads("\n".join(lines[idx:]))
    raise AssertionError(f"No JSON payload found in output: {text!r}")


def test_cli_help(runner):
    """Test CLI help command."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "KubeStellar Agent" in result.output


def test_list_functions(runner):
    """Test listing available functions."""
    result = runner.invoke(cli, ["list-functions"])
    assert result.exit_code == 0
    assert "Available functions:" in result.output
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
    output = _load_json_from_output(result.output)
    assert "error" in output or "kubeconfig_path" in output


def test_execute_function_with_json_params(runner):
    """Test executing a function with JSON parameters."""
    params = json.dumps(
        {"kubeconfig_path": "/nonexistent/path", "detail_level": "full"}
    )
    result = runner.invoke(cli, ["execute", "get_kubeconfig", "--params", params])
    assert result.exit_code == 0
    output = _load_json_from_output(result.output)
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


def test_execute_with_mode_override(runner):
    """Mode flag should reinitialize providers and log selection."""
    result = runner.invoke(
        cli,
        [
            "execute",
            "--mode",
            "kubestellar",
            "get_kubeconfig",
            "--param",
            "kubeconfig_path=/nonexistent/path",
        ],
    )
    assert result.exit_code == 0
    assert "* Using mode: kubestellar" in result.output
    _load_json_from_output(result.output)


def test_describe_with_kubeconfig_override(runner):
    """Kubeconfig flag should emit mode information to stderr."""
    result = runner.invoke(
        cli,
        [
            "describe",
            "--kubeconfig",
            "/tmp/nonexistent-kubeconfig",
            "get_kubeconfig",
        ],
    )
    assert result.exit_code == 0
    assert "* Using mode:" in result.output
    assert "Function: get_kubeconfig" in result.output
