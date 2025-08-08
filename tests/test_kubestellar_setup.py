"""Tests for KubeStellar setup functionality."""

from unittest.mock import patch

import pytest

from src.shared.functions.kubestellar_setup import (
    KubeStellarSetupFunction,
    PrerequisiteCheck,
    SetupProgress,
)


class TestKubeStellarSetupFunction:
    """Test cases for KubeStellar setup function."""

    @pytest.fixture
    def setup_function(self):
        """Create a KubeStellar setup function instance."""
        return KubeStellarSetupFunction()

    @pytest.mark.asyncio
    async def test_verify_prerequisites_all_installed(self, setup_function):
        """Test prerequisite verification when all tools are installed."""
        # Mock successful command execution for all tools
        mock_responses = {
            "kubectl": {
                "returncode": 0,
                "stdout": '{"clientVersion": {"gitVersion": "v1.28.0"}}',
                "stderr": "",
            },
            "helm": {
                "returncode": 0,
                "stdout": "v3.12.0+g123456",
                "stderr": "",
            },
            "docker": {
                "returncode": 0,
                "stdout": '{"Client": {"Version": "24.0.0"}}',
                "stderr": "",
            },
            "kind": {
                "returncode": 0,
                "stdout": "kind v0.20.0 go1.20.4 linux/amd64",
                "stderr": "",
            },
            "kflex": {
                "returncode": 0,
                "stdout": "kflex version v0.6.0",
                "stderr": "",
            },
            "clusteradm": {
                "returncode": 0,
                "stdout": "clusteradm version v0.4.0",
                "stderr": "",
            },
        }

        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/local/bin/tool"
            
            with patch.object(setup_function, "_run_command") as mock_run:
                def side_effect(cmd):
                    tool_name = cmd[0]
                    return mock_responses.get(tool_name, {"returncode": 1, "stdout": "", "stderr": "not found"})
                
                mock_run.side_effect = side_effect
                
                result = await setup_function._verify_prerequisites("detailed")
                
                assert result["status"] == "success"
                assert result["summary"]["passed"] >= 5  # At least kubectl, helm, docker, kind, kflex, clusteradm
                assert len(result["missing_required"]) == 0

    @pytest.mark.asyncio
    async def test_verify_prerequisites_missing_required(self, setup_function):
        """Test prerequisite verification when required tools are missing."""
        with patch("shutil.which") as mock_which:
            # Simulate kubectl missing
            def which_side_effect(tool):
                if tool == "kubectl":
                    return None
                return "/usr/local/bin/tool"
            
            mock_which.side_effect = which_side_effect
            
            result = await setup_function._verify_prerequisites("detailed")
            
            assert result["status"] == "error"
            assert "kubectl" in result["missing_required"]
            assert "installation_instructions" in result
            assert "kubectl" in result["installation_instructions"]

    @pytest.mark.asyncio
    async def test_cleanup_existing_clusters_kind(self, setup_function):
        """Test cleanup of existing kind clusters."""
        mock_list_response = {
            "returncode": 0,
            "stdout": "kubeflex\ncluster1\ncluster2\nother-cluster",
            "stderr": "",
        }
        
        mock_delete_response = {
            "returncode": 0,
            "stdout": "Deleting cluster...",
            "stderr": "",
        }

        with patch.object(setup_function, "_run_command") as mock_run:
            def side_effect(cmd):
                if cmd == ["kind", "get", "clusters"]:
                    return mock_list_response
                elif cmd[0:3] == ["kind", "delete", "cluster"]:
                    return mock_delete_response
                elif cmd[0:3] == ["kubectl", "config", "get-contexts"]:
                    return {"returncode": 0, "stdout": "kind-kubeflex\nkind-cluster1\nkind-cluster2", "stderr": ""}
                elif cmd[0:3] == ["kubectl", "config", "delete-context"]:
                    return {"returncode": 0, "stdout": "", "stderr": ""}
                return {"returncode": 1, "stdout": "", "stderr": "unknown command"}
            
            mock_run.side_effect = side_effect
            
            result = await setup_function._cleanup_existing_clusters("kind", "detailed")
            
            assert result["status"] == "success"
            assert len(result["clusters_removed"]) == 3  # kubeflex, cluster1, cluster2
            assert "kubeflex" in result["clusters_removed"]
            assert "cluster1" in result["clusters_removed"]
            assert "cluster2" in result["clusters_removed"]

    @pytest.mark.asyncio
    async def test_create_kubeflex_cluster_success(self, setup_function):
        """Test successful KubeFlex cluster creation."""
        mock_create_response = {
            "returncode": 0,
            "stdout": "Creating cluster 'kubeflex'...",
            "stderr": "",
        }

        with patch.object(setup_function, "_run_command") as mock_run:
            with patch.object(setup_function, "_wait_for_cluster_ready", return_value=True):
                def side_effect(cmd):
                    if cmd == ["kind", "create", "cluster", "--name", "kubeflex"]:
                        return mock_create_response
                    return {"returncode": 0, "stdout": "", "stderr": ""}
                
                mock_run.side_effect = side_effect
                
                result = await setup_function._create_kubeflex_cluster("kind", "kubeflex", "v0.28.0", False, "detailed")
                
                assert result["status"] == "success"
                assert result["cluster_name"] == "kubeflex"
                assert result["platform"] == "kind"
                assert any(step["step"] == "create_cluster" for step in result["steps"])

    @pytest.mark.asyncio
    async def test_create_kubeflex_cluster_failure(self, setup_function):
        """Test KubeFlex cluster creation failure."""
        mock_create_response = {
            "returncode": 1,
            "stdout": "",
            "stderr": "Failed to create cluster",
        }

        with patch.object(setup_function, "_run_command", return_value=mock_create_response):
            result = await setup_function._create_kubeflex_cluster("kind", "kubeflex", "v0.28.0", False, "detailed")
            
            assert result["status"] == "error"
            assert "Failed to create kind cluster" in result["error"]

    @pytest.mark.asyncio
    async def test_install_kubestellar_components_success(self, setup_function):
        """Test successful KubeStellar components installation."""
        mock_responses = {
            "switch_context": {"returncode": 0, "stdout": "", "stderr": ""},
            "helm_repo_add": {"returncode": 0, "stdout": "", "stderr": ""},
            "helm_repo_update": {"returncode": 0, "stdout": "", "stderr": ""},
            "helm_install": {"returncode": 0, "stdout": "Release installed successfully", "stderr": ""},
        }

        with patch.object(setup_function, "_run_command") as mock_run:
            with patch.object(setup_function, "_wait_for_its_ready", return_value=True):
                def side_effect(cmd, timeout=None):
                    if cmd == ["kubectl", "config", "use-context", "kind-kubeflex"]:
                        return mock_responses["switch_context"]
                    elif cmd == ["helm", "repo", "add", "kubestellar", "https://kubestellar.github.io/kubestellar"]:
                        return mock_responses["helm_repo_add"]
                    elif cmd == ["helm", "repo", "update"]:
                        return mock_responses["helm_repo_update"]
                    elif len(cmd) >= 4 and cmd[0:4] == ["helm", "upgrade", "--install", "kubestellar-core"]:
                        return mock_responses["helm_install"]
                    return {"returncode": 0, "stdout": "", "stderr": ""}
                
                mock_run.side_effect = side_effect
                
                result = await setup_function._install_kubestellar_components("kubeflex", "v0.28.0", "10m", True)
                
                assert result["status"] == "success"
                assert "kubestellar-core" in result["components_installed"]
                assert any(step["step"] == "install_core" for step in result["steps"])

    @pytest.mark.asyncio
    async def test_setup_wec_clusters_success(self, setup_function):
        """Test successful WEC cluster setup."""
        mock_create_response = {
            "returncode": 0,
            "stdout": "Creating cluster...",
            "stderr": "",
        }
        
        mock_register_response = {
            "status": "success",
            "cluster_name": "cluster1",
        }

        with patch.object(setup_function, "_run_command", return_value=mock_create_response):
            with patch.object(setup_function, "_wait_for_cluster_ready", return_value=True):
                with patch.object(setup_function, "_register_wec_cluster", return_value=mock_register_response):
                    result = await setup_function._setup_wec_clusters("kind", ["cluster1", "cluster2"], True, "detailed")
                    
                    assert result["status"] == "success"
                    assert len(result["clusters_created"]) == 2
                    assert "cluster1" in result["clusters_created"]
                    assert "cluster2" in result["clusters_created"]
                    assert len(result["clusters_registered"]) == 2

    @pytest.mark.asyncio
    async def test_automated_setup_success(self, setup_function):
        """Test successful automated setup."""
        mock_download_response = {
            "returncode": 0,
            "stdout": "#!/bin/bash\necho 'Setup script content'",
            "stderr": "",
        }
        
        mock_script_response = {
            "returncode": 0,
            "stdout": "Setup completed successfully",
            "stderr": "",
        }

        with patch.object(setup_function, "_run_command") as mock_run:
            def side_effect(cmd, timeout=None):
                if cmd == ["curl", "-s", "https://raw.githubusercontent.com/kubestellar/kubestellar/refs/tags/v0.28.0/scripts/create-kubestellar-demo-env.sh"]:
                    return mock_download_response
                elif len(cmd) >= 2 and cmd[0] == "bash" and "-c" in cmd[1]:
                    return mock_script_response
                return {"returncode": 0, "stdout": "", "stderr": ""}
            
            mock_run.side_effect = side_effect
            
            result = await setup_function._automated_setup("kind", "v0.28.0", "detailed")
            
            assert result["status"] == "success"
            assert result["setup_type"] == "automated"
            assert result["platform"] == "kind"
            assert result["version"] == "v0.28.0"

    @pytest.mark.asyncio
    async def test_full_setup_manual_success(self, setup_function):
        """Test successful full manual setup."""
        # Mock all the individual operations
        mock_prereq_result = {"status": "success", "missing_required": []}
        mock_cleanup_result = {"status": "success", "clusters_removed": []}
        mock_kubeflex_result = {"status": "success", "cluster_name": "kubeflex"}
        mock_install_result = {"status": "success", "components_installed": ["kubestellar-core"]}
        mock_wec_result = {"status": "success", "clusters_created": ["cluster1", "cluster2"]}
        mock_verify_result = {"status": "success", "checks": []}

        with patch.object(setup_function, "_verify_prerequisites", return_value=mock_prereq_result):
            with patch.object(setup_function, "_cleanup_existing_clusters", return_value=mock_cleanup_result):
                with patch.object(setup_function, "_create_kubeflex_cluster", return_value=mock_kubeflex_result):
                    with patch.object(setup_function, "_install_kubestellar_components", return_value=mock_install_result):
                        with patch.object(setup_function, "_setup_wec_clusters", return_value=mock_wec_result):
                            with patch.object(setup_function, "_verify_complete_setup", return_value=mock_verify_result):
                                result = await setup_function._manual_full_setup(
                                    "kind", "kubeflex", "v0.28.0", True, True, "10m", True, True, ["cluster1", "cluster2"], "detailed"
                                )
                                
                                assert result["status"] == "success"
                                assert result["setup_type"] == "manual"
                                assert "kubeflex" in result["clusters_created"]
                                assert "cluster1" in result["clusters_created"]
                                assert "cluster2" in result["clusters_created"]
                                assert len(result["steps_completed"]) == 6  # All steps completed

    @pytest.mark.asyncio
    async def test_version_parsing(self, setup_function):
        """Test version parsing for different tools."""
        test_cases = [
            ("kubectl", '{"clientVersion": {"gitVersion": "v1.28.0"}}', "1.28.0"),
            ("helm", "v3.12.0+g123456", "3.12.0"),
            ("docker", '{"Client": {"Version": "24.0.0"}}', "24.0.0"),
            ("kind", "kind v0.20.0 go1.20.4 linux/amd64", "0.20.0"),
            ("kflex", "kflex version v0.6.0", "0.6.0"),
        ]
        
        for tool, output, expected_version in test_cases:
            parsed_version = setup_function._parse_version(tool, output)
            assert parsed_version == expected_version, f"Failed to parse version for {tool}: expected {expected_version}, got {parsed_version}"

    def test_version_comparison(self, setup_function):
        """Test version comparison logic."""
        test_cases = [
            ("1.28.0", "1.26.0", True),   # current > minimum
            ("1.26.0", "1.26.0", True),   # current == minimum
            ("1.25.0", "1.26.0", False),  # current < minimum
            ("3.12.0", "3.8.0", True),    # current > minimum
            ("unknown", "1.0.0", False),  # unknown version
        ]
        
        for current, minimum, expected in test_cases:
            result = setup_function._version_meets_minimum(current, minimum)
            assert result == expected, f"Version comparison failed: {current} vs {minimum}, expected {expected}, got {result}"

    @pytest.mark.asyncio
    async def test_wait_for_cluster_ready_timeout(self, setup_function):
        """Test cluster readiness check timeout."""
        mock_response = {
            "returncode": 1,
            "stdout": "",
            "stderr": "Connection refused",
        }

        with patch.object(setup_function, "_run_command", return_value=mock_response):
            result = await setup_function._wait_for_cluster_ready("test-cluster", timeout=1)  # 1 second timeout
            assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_cluster_ready_success(self, setup_function):
        """Test successful cluster readiness check."""
        mock_response = {
            "returncode": 0,
            "stdout": "Kubernetes control plane is running",
            "stderr": "",
        }

        with patch.object(setup_function, "_run_command", return_value=mock_response):
            result = await setup_function._wait_for_cluster_ready("test-cluster", timeout=10)
            assert result is True

    @pytest.mark.asyncio
    async def test_get_installation_instructions(self, setup_function):
        """Test generation of installation instructions."""
        missing_tools = ["kubectl", "helm", "kind or k3d"]
        instructions = setup_function._get_installation_instructions(missing_tools)
        
        assert "kubectl" in instructions
        assert "helm" in instructions
        assert "kind_or_k3d" in instructions
        assert "curl -LO" in instructions["kubectl"]
        assert "helm/helm" in instructions["helm"]

    def test_schema_validation(self, setup_function):
        """Test that the function schema is valid."""
        schema = setup_function.get_schema()
        
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "operation" in schema["properties"]
        assert "platform" in schema["properties"]
        assert "cluster_name" in schema["properties"]
        
        # Check enum values
        assert "full_setup" in schema["properties"]["operation"]["enum"]
        assert "verify_prerequisites" in schema["properties"]["operation"]["enum"]
        assert "kind" in schema["properties"]["platform"]["enum"]
        assert "k3d" in schema["properties"]["platform"]["enum"]

    @pytest.mark.asyncio
    async def test_error_handling_invalid_operation(self, setup_function):
        """Test error handling for invalid operations."""
        result = await setup_function.execute(operation="invalid_operation")
        
        assert result["status"] == "error"
        assert "Unsupported operation" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_verify_prerequisites_operation(self, setup_function):
        """Test execute function with verify_prerequisites operation."""
        with patch.object(setup_function, "_verify_prerequisites") as mock_verify:
            mock_verify.return_value = {"status": "success", "checks": []}
            
            result = await setup_function.execute(operation="verify_prerequisites")
            
            mock_verify.assert_called_once_with("detailed")
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_execute_cleanup_operation(self, setup_function):
        """Test execute function with cleanup operation."""
        with patch.object(setup_function, "_cleanup_existing_clusters") as mock_cleanup:
            mock_cleanup.return_value = {"status": "success", "clusters_removed": []}
            
            result = await setup_function.execute(operation="cleanup", platform="kind")
            
            mock_cleanup.assert_called_once_with("kind", "detailed")
            assert result["status"] == "success"


class TestPrerequisiteCheck:
    """Test cases for PrerequisiteCheck dataclass."""

    def test_prerequisite_check_creation(self):
        """Test creating PrerequisiteCheck instances."""
        check = PrerequisiteCheck(
            name="kubectl",
            installed=True,
            version="1.28.0",
            path="/usr/local/bin/kubectl"
        )
        
        assert check.name == "kubectl"
        assert check.installed is True
        assert check.version == "1.28.0"
        assert check.path == "/usr/local/bin/kubectl"
        assert check.error == ""

    def test_prerequisite_check_with_error(self):
        """Test PrerequisiteCheck with error."""
        check = PrerequisiteCheck(
            name="missing-tool",
            installed=False,
            error="Tool not found in PATH"
        )
        
        assert check.name == "missing-tool"
        assert check.installed is False
        assert check.error == "Tool not found in PATH"


class TestSetupProgress:
    """Test cases for SetupProgress dataclass."""

    def test_setup_progress_creation(self):
        """Test creating SetupProgress instances."""
        progress = SetupProgress(
            step="create_cluster",
            status="completed",
            message="Cluster created successfully",
            duration=30.5
        )
        
        assert progress.step == "create_cluster"
        assert progress.status == "completed"
        assert progress.message == "Cluster created successfully"
        assert progress.duration == 30.5
        assert progress.error == ""


if __name__ == "__main__":
    pytest.main([__file__])