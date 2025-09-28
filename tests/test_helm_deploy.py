"""Tests for Helm deployment function."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.shared.functions.helm_deploy import HelmDeployFunction


@pytest.fixture
def helm_function():
    """Create HelmDeployFunction instance for testing."""
    return HelmDeployFunction()


@pytest.fixture
def mock_clusters():
    """Mock clusters for testing."""
    return [
        {"name": "cluster1", "context": "cluster1", "status": "Ready"},
        {"name": "cluster2", "context": "cluster2", "status": "Ready"},
        {"name": "edge-cluster1", "context": "edge-cluster1", "status": "Ready"},
    ]


@pytest.fixture
def mock_namespaces():
    """Mock namespaces for testing."""
    return ["default", "kube-system", "app-namespace"]


class TestHelmDeployFunction:
    """Test Helm deployment function."""

    def test_initialization(self, helm_function):
        """Test HelmDeployFunction initialization."""
        assert helm_function.name == "helm_deploy"
        assert "Helm charts" in helm_function.description
        assert "KubeStellar" in helm_function.description

    def test_schema_validation(self, helm_function):
        """Test function schema."""
        schema = helm_function.get_schema()
        assert schema["type"] == "object"

        # Check required properties exist
        properties = schema["properties"]
        assert "chart_name" in properties
        assert "operation" in properties
        assert "target_clusters" in properties
        assert "namespace" in properties
        assert "create_binding_policy" in properties

        # Check operation enum
        assert properties["operation"]["enum"] == [
            "install",
            "upgrade",
            "uninstall",
            "status",
            "history",
        ]
        assert properties["operation"]["default"] == "install"

        # Check boolean defaults
        assert properties["create_binding_policy"]["default"] is True
        assert properties["wait"]["default"] is True
        assert properties["create_namespace"]["default"] is True

    def test_validate_inputs_install_missing_chart(self, helm_function):
        """Test input validation for install operation without chart."""
        result = helm_function._validate_inputs("", "", "", "", "install", "release1")
        assert result["status"] == "error"
        assert "chart_name or chart_path must be specified" in result["error"]

    def test_validate_inputs_install_missing_repository(self, helm_function):
        """Test input validation for install with chart name but no repository."""
        result = helm_function._validate_inputs(
            "nginx", "", "", "", "install", "release1"
        )
        assert result["status"] == "error"
        assert (
            "repository_url, repository_name, or chart_path must be specified"
            in result["error"]
        )

    def test_validate_inputs_valid_install(self, helm_function):
        """Test valid input validation for install operation."""
        result = helm_function._validate_inputs(
            "nginx", "", "https://charts.bitnami.com/bitnami", "", "install", "release1"
        )
        assert result is None

    def test_validate_inputs_status_missing_release(self, helm_function):
        """Test input validation for status operation without release name."""
        result = helm_function._validate_inputs("", "", "", "", "status", "")
        assert result["status"] == "error"
        assert "release_name is required" in result["error"]

    def test_prepare_kubestellar_labels(self, helm_function):
        """Test KubeStellar label preparation."""
        labels = helm_function._prepare_kubestellar_labels(
            "myapp", "bitnami/nginx", {"custom": "value"}
        )

        expected_labels = {
            "app.kubernetes.io/managed-by": "Helm",
            "app.kubernetes.io/instance": "myapp",
            "app.kubernetes.io/name": "nginx",
            "kubestellar.io/helm-chart": "bitnami-nginx",
            "kubestellar.io/helm-release": "myapp",
            "custom": "value",
        }

        assert labels == expected_labels

    def test_prepare_kubestellar_labels_no_chart(self, helm_function):
        """Test KubeStellar label preparation without chart name."""
        labels = helm_function._prepare_kubestellar_labels("myapp", "", None)

        expected_labels = {
            "app.kubernetes.io/managed-by": "Helm",
            "app.kubernetes.io/instance": "myapp",
            "kubestellar.io/helm-chart": "myapp",
            "kubestellar.io/helm-release": "myapp",
        }

        assert labels == expected_labels

    def test_parse_cluster_values(self, helm_function):
        """Test parsing cluster-specific values."""
        cluster_values = ["cluster1=values1.yaml", "cluster2=values2.yaml"]
        result = helm_function._parse_cluster_values(cluster_values)

        expected = {
            "cluster1": "values1.yaml",
            "cluster2": "values2.yaml",
        }

        assert result == expected

    def test_parse_cluster_set_values(self, helm_function):
        """Test parsing cluster-specific set values."""
        cluster_set_values = [
            "cluster1=image.tag=v1.0",
            "cluster1=replicas=3",
            "cluster2=image.tag=v2.0",
        ]
        result = helm_function._parse_cluster_set_values(cluster_set_values)

        expected = {
            "cluster1": ["image.tag=v1.0", "replicas=3"],
            "cluster2": ["image.tag=v2.0"],
        }

        assert result == expected

    def test_filter_clusters_by_names(self, helm_function, mock_clusters):
        """Test filtering clusters by names."""
        result = helm_function._filter_clusters(
            mock_clusters, ["cluster1", "edge-cluster1"], None
        )

        assert len(result) == 2
        assert result[0]["name"] == "cluster1"
        assert result[1]["name"] == "edge-cluster1"

    def test_filter_clusters_by_labels(self, helm_function, mock_clusters):
        """Test filtering clusters by labels."""
        # This should return all clusters (mock implementation)
        result = helm_function._filter_clusters(mock_clusters, None, ["location=edge"])

        assert len(result) == 3  # Mock implementation returns all

    def test_is_wds_cluster(self, helm_function):
        """Test WDS cluster detection."""
        assert helm_function._is_wds_cluster("wds-cluster1") is True
        assert helm_function._is_wds_cluster("my-wds-cluster") is True
        assert helm_function._is_wds_cluster("cluster_wds_test") is True
        assert helm_function._is_wds_cluster("regular-cluster") is False

    @pytest.mark.asyncio
    async def test_run_command_success(self, helm_function):
        """Test successful command execution."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock process
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"success output", b"")
            mock_subprocess.return_value = mock_process

            result = await helm_function._run_command(["echo", "test"])

            assert result["returncode"] == 0
            assert result["stdout"] == "success output"
            assert result["stderr"] == ""

    @pytest.mark.asyncio
    async def test_run_command_failure(self, helm_function):
        """Test failed command execution."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock process
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"error output")
            mock_subprocess.return_value = mock_process

            result = await helm_function._run_command(["false"])

            assert result["returncode"] == 1
            assert result["stdout"] == ""
            assert result["stderr"] == "error output"

    @pytest.mark.asyncio
    async def test_discover_clusters(self, helm_function):
        """Test cluster discovery."""
        with patch.object(helm_function, "_run_command") as mock_run:
            # Mock kubectl config get-contexts
            mock_run.side_effect = [
                {
                    "returncode": 0,
                    "stdout": "cluster1\ncluster2\nwds-cluster\n",
                    "stderr": "",
                },
                {
                    "returncode": 0,
                    "stdout": "cluster info",
                    "stderr": "",
                },  # cluster1 test
                {
                    "returncode": 0,
                    "stdout": "cluster info",
                    "stderr": "",
                },  # cluster2 test
                {
                    "returncode": 0,
                    "stdout": "cluster info",
                    "stderr": "",
                },  # wds-cluster test (will be skipped)
            ]

            result = await helm_function._discover_clusters("", "")

            assert len(result) == 2  # wds-cluster should be filtered out
            assert result[0]["name"] == "cluster1"
            assert result[1]["name"] == "cluster2"

    @pytest.mark.asyncio
    async def test_resolve_target_namespaces_specific(
        self, helm_function, mock_clusters
    ):
        """Test resolving specific target namespaces."""
        result = await helm_function._resolve_target_namespaces(
            mock_clusters[0], False, "", ["ns1", "ns2"], "", ""
        )

        assert result == ["ns1", "ns2"]

    @pytest.mark.asyncio
    async def test_resolve_target_namespaces_all(self, helm_function, mock_clusters):
        """Test resolving all namespaces."""
        with patch.object(helm_function, "_run_command") as mock_run:
            mock_run.return_value = {
                "returncode": 0,
                "stdout": "default kube-system app-namespace",
                "stderr": "",
            }

            result = await helm_function._resolve_target_namespaces(
                mock_clusters[0], True, "", None, "", ""
            )

            assert result == ["default", "kube-system", "app-namespace"]

    @pytest.mark.asyncio
    async def test_resolve_target_namespaces_default(
        self, helm_function, mock_clusters
    ):
        """Test resolving default namespace."""
        result = await helm_function._resolve_target_namespaces(
            mock_clusters[0], False, "", None, "custom-ns", ""
        )

        assert result == ["custom-ns"]

    @pytest.mark.asyncio
    async def test_build_helm_command_install(self, helm_function):
        """Test building Helm install command."""
        cluster = {"name": "test-cluster", "context": "test-context"}
        labels = {"app.kubernetes.io/managed-by": "Helm"}

        cmd = await helm_function._build_helm_command(
            operation="install",
            release_name="myapp",
            chart_name="nginx",
            chart_version="1.0.0",
            repository_url="https://charts.bitnami.com/bitnami",
            repository_name="",
            chart_path="",
            cluster=cluster,
            namespace="default",
            values_file="values.yaml",
            values_files=None,
            cluster_values_map={},
            set_values=["replicas=3"],
            cluster_set_values_map={},
            wait=True,
            timeout="5m",
            atomic=False,
            kubeconfig="",
            helm_labels=labels,
        )

        expected_cmd = [
            "helm",
            "install",
            "myapp",
            "--repo",
            "https://charts.bitnami.com/bitnami",
            "nginx",
            "--version",
            "1.0.0",
            "-f",
            "values.yaml",
            "--set",
            "replicas=3",
            "--set",
            "labels.app.kubernetes.io/managed-by=Helm",
            "--wait",
            "--timeout",
            "5m",
            "--kube-context",
            "test-context",
            "--namespace",
            "default",
        ]

        assert cmd == expected_cmd

    @pytest.mark.asyncio
    async def test_build_helm_command_upgrade(self, helm_function):
        """Test building Helm upgrade command."""
        cluster = {"name": "test-cluster", "context": "test-context"}
        labels = {}

        cmd = await helm_function._build_helm_command(
            operation="upgrade",
            release_name="myapp",
            chart_name="nginx",
            chart_version="",
            repository_url="",
            repository_name="bitnami",
            chart_path="",
            cluster=cluster,
            namespace="default",
            values_file="",
            values_files=None,
            cluster_values_map={},
            set_values=None,
            cluster_set_values_map={},
            wait=False,
            timeout="5m",
            atomic=True,
            kubeconfig="/path/to/kubeconfig",
            helm_labels=labels,
        )

        expected_cmd = [
            "helm",
            "upgrade",
            "myapp",
            "bitnami/nginx",
            "--timeout",
            "5m",
            "--atomic",
            "--install",
            "--kube-context",
            "test-context",
            "--namespace",
            "default",
            "--kubeconfig",
            "/path/to/kubeconfig",
        ]

        assert cmd == expected_cmd

    @pytest.mark.asyncio
    async def test_build_helm_command_uninstall(self, helm_function):
        """Test building Helm uninstall command."""
        cluster = {"name": "test-cluster", "context": "test-context"}
        labels = {}

        cmd = await helm_function._build_helm_command(
            operation="uninstall",
            release_name="myapp",
            chart_name="",
            chart_version="",
            repository_url="",
            repository_name="",
            chart_path="",
            cluster=cluster,
            namespace="default",
            values_file="",
            values_files=None,
            cluster_values_map={},
            set_values=None,
            cluster_set_values_map={},
            wait=False,
            timeout="",
            atomic=False,
            kubeconfig="",
            helm_labels=labels,
        )

        expected_cmd = [
            "helm",
            "uninstall",
            "myapp",
            "--kube-context",
            "test-context",
            "--namespace",
            "default",
        ]

        assert cmd == expected_cmd

    @pytest.mark.asyncio
    async def test_ensure_namespace_exists_already_exists(self, helm_function):
        """Test ensuring namespace exists when it already exists."""
        cluster = {"name": "test-cluster", "context": "test-context"}
        labels = {"key": "value"}

        with patch.object(helm_function, "_run_command") as mock_run:
            # Namespace exists
            mock_run.side_effect = [
                {"returncode": 0, "stdout": "", "stderr": ""},  # namespace exists
                {"returncode": 0, "stdout": "", "stderr": ""},  # label command
            ]

            await helm_function._ensure_namespace_exists(cluster, "test-ns", "", labels)

            # Should call get namespace and label commands
            assert mock_run.call_count == 2

    @pytest.mark.asyncio
    async def test_ensure_namespace_exists_create_new(self, helm_function):
        """Test ensuring namespace exists when it needs to be created."""
        cluster = {"name": "test-cluster", "context": "test-context"}
        labels = {"key": "value"}

        with patch.object(helm_function, "_run_command") as mock_run:
            # Namespace doesn't exist, then create it, then label it
            mock_run.side_effect = [
                {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "not found",
                },  # namespace doesn't exist
                {"returncode": 0, "stdout": "", "stderr": ""},  # create namespace
                {"returncode": 0, "stdout": "", "stderr": ""},  # label command
            ]

            await helm_function._ensure_namespace_exists(cluster, "test-ns", "", labels)

            # Should call get, create, and label commands
            assert mock_run.call_count == 3

    @pytest.mark.asyncio
    async def test_label_helm_secret(self, helm_function):
        """Test labeling Helm secret."""
        cluster = {"name": "test-cluster", "context": "test-context"}
        labels = {"key": "value"}

        with patch.object(helm_function, "_run_command") as mock_run:
            # Mock getting secret name and labeling it
            mock_run.side_effect = [
                {
                    "returncode": 0,
                    "stdout": "sh.helm.release.v1.myapp.v1",
                    "stderr": "",
                },  # get secret
                {"returncode": 0, "stdout": "", "stderr": ""},  # label secret
            ]

            await helm_function._label_helm_secret(
                cluster, "default", "myapp", labels, ""
            )

            assert mock_run.call_count == 2

    @pytest.mark.asyncio
    async def test_parse_helm_output(self, helm_function):
        """Test parsing Helm command output."""
        cluster = {"name": "test-cluster", "context": "test-context"}

        with patch.object(helm_function, "_run_command") as mock_run:
            # Mock helm status output
            status_data = {
                "name": "myapp",
                "version": 1,
                "info": {"status": "deployed"},
                "chart": {
                    "metadata": {
                        "name": "nginx",
                        "version": "1.0.0",
                        "appVersion": "1.21.0",
                    }
                },
            }

            mock_run.return_value = {
                "returncode": 0,
                "stdout": json.dumps(status_data),
                "stderr": "",
            }

            result = await helm_function._parse_helm_output(
                "install output", "install", "myapp", cluster, "default", ""
            )

            expected = {
                "release_name": "myapp",
                "revision": 1,
                "status": "deployed",
                "chart_name": "nginx",
                "chart_version": "1.0.0",
                "app_version": "1.21.0",
            }

            assert result == expected

    @pytest.mark.asyncio
    async def test_create_binding_policy(self, helm_function):
        """Test creating KubeStellar binding policy."""
        helm_labels = {
            "app.kubernetes.io/managed-by": "Helm",
            "app.kubernetes.io/instance": "myapp",
            "kubestellar.io/helm-chart": "nginx",
        }
        cluster_selector_labels = {"location-group": "edge"}

        with patch.object(helm_function, "_run_command") as mock_run:
            mock_run.return_value = {
                "returncode": 0,
                "stdout": "bindingpolicy.control.kubestellar.io/myapp-helm-policy created",
                "stderr": "",
            }

            result = await helm_function._create_binding_policy(
                "myapp-helm-policy",
                "myapp",
                helm_labels,
                cluster_selector_labels,
                ["default"],
                "wds-context",
                "",
            )

            assert result["status"] == "success"
            assert result["policy_name"] == "myapp-helm-policy"
            assert "clusterSelectors" in str(result["policy_spec"])

    @pytest.mark.asyncio
    async def test_execute_dry_run(self, helm_function):
        """Test dry run execution."""
        with (
            patch.object(helm_function, "_discover_clusters") as mock_discover,
            patch.object(helm_function, "_resolve_target_namespaces") as mock_resolve,
        ):

            mock_discover.return_value = [
                {"name": "cluster1", "context": "cluster1", "status": "Ready"}
            ]
            mock_resolve.return_value = ["default"]

            result = await helm_function.execute(
                chart_name="nginx",
                repository_url="https://charts.bitnami.com/bitnami",
                target_clusters=["cluster1"],
                dry_run=True,
            )

            assert result["status"] == "success"
            assert "DRY RUN" in result["message"]
            assert "deployment_plan" in result

    @pytest.mark.asyncio
    async def test_execute_install_success(self, helm_function):
        """Test successful Helm install execution."""
        with (
            patch.object(helm_function, "_discover_clusters") as mock_discover,
            patch.object(helm_function, "_resolve_target_namespaces") as mock_resolve,
            patch.object(helm_function, "_deploy_helm_chart") as mock_deploy,
            patch.object(helm_function, "_create_binding_policy") as mock_policy,
        ):

            mock_discover.return_value = [
                {"name": "cluster1", "context": "cluster1", "status": "Ready"}
            ]
            mock_resolve.return_value = ["default"]
            mock_deploy.return_value = {"status": "success", "clusters_succeeded": 1}
            mock_policy.return_value = {
                "status": "success",
                "policy_name": "nginx-helm-policy",
            }

            result = await helm_function.execute(
                chart_name="nginx",
                repository_url="https://charts.bitnami.com/bitnami",
                target_clusters=["cluster1"],
                operation="install",
            )

            assert result["status"] == "success"
            assert result["binding_policy"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_execute_validation_error(self, helm_function):
        """Test execution with validation error."""
        result = await helm_function.execute(operation="install")

        assert result["status"] == "error"
        assert "chart_name or chart_path must be specified" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_no_clusters(self, helm_function):
        """Test execution when no clusters are discovered."""
        with patch.object(helm_function, "_discover_clusters") as mock_discover:
            mock_discover.return_value = []

            result = await helm_function.execute(
                chart_name="nginx",
                repository_url="https://charts.bitnami.com/bitnami",
            )

            assert result["status"] == "error"
            assert "No clusters discovered" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_no_matching_clusters(self, helm_function):
        """Test execution when no clusters match selection criteria."""
        with patch.object(helm_function, "_discover_clusters") as mock_discover:
            mock_discover.return_value = [
                {"name": "cluster1", "context": "cluster1", "status": "Ready"}
            ]

            result = await helm_function.execute(
                chart_name="nginx",
                repository_url="https://charts.bitnami.com/bitnami",
                target_clusters=["nonexistent-cluster"],
            )

            assert result["status"] == "error"
            assert "No clusters match the selection criteria" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_uninstall_operation(self, helm_function):
        """Test uninstall operation execution."""
        with (
            patch.object(helm_function, "_discover_clusters") as mock_discover,
            patch.object(helm_function, "_resolve_target_namespaces") as mock_resolve,
            patch.object(helm_function, "_uninstall_helm_chart") as mock_uninstall,
        ):

            mock_discover.return_value = [
                {"name": "cluster1", "context": "cluster1", "status": "Ready"}
            ]
            mock_resolve.return_value = ["default"]
            mock_uninstall.return_value = {
                "status": "success",
                "operation": "uninstall",
            }

            result = await helm_function.execute(
                release_name="nginx",
                target_clusters=["cluster1"],
                operation="uninstall",
            )

            assert result["status"] == "success"
            assert result["operation"] == "uninstall"

    @pytest.mark.asyncio
    async def test_execute_status_operation(self, helm_function):
        """Test status operation execution."""
        with (
            patch.object(helm_function, "_discover_clusters") as mock_discover,
            patch.object(helm_function, "_resolve_target_namespaces") as mock_resolve,
            patch.object(helm_function, "_get_helm_info") as mock_info,
        ):

            mock_discover.return_value = [
                {"name": "cluster1", "context": "cluster1", "status": "Ready"}
            ]
            mock_resolve.return_value = ["default"]
            mock_info.return_value = {"status": "success", "operation": "status"}

            result = await helm_function.execute(
                release_name="nginx",
                target_clusters=["cluster1"],
                operation="status",
            )

            assert result["status"] == "success"
            assert result["operation"] == "status"


@pytest.mark.asyncio
async def test_integration_helm_function_registry():
    """Test integration with function registry."""
    from src.shared.base_functions import FunctionRegistry

    registry = FunctionRegistry()
    helm_func = HelmDeployFunction()
    registry.register(helm_func)

    # Test retrieval
    retrieved = registry.get("helm_deploy")
    assert retrieved is not None
    assert retrieved.name == "helm_deploy"

    # Test schema
    schemas = registry.get_schemas()
    assert "helm_deploy" in schemas
    assert schemas["helm_deploy"]["type"] == "object"
