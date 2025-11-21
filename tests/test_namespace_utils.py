"""Tests for namespace utilities functionality."""

import json
from unittest.mock import patch

import pytest

from src.shared.functions.namespace_utils import NamespaceUtilsFunction


@pytest.fixture
def namespace_function():
    """Create a namespace utils function instance."""
    return NamespaceUtilsFunction()


@pytest.fixture
def mock_clusters():
    """Mock cluster data."""
    return [
        {"name": "cluster1", "context": "cluster1", "status": "Ready"},
        {"name": "cluster2", "context": "cluster2", "status": "Ready"},
    ]


@pytest.fixture
def mock_namespace_json():
    """Mock namespace JSON response."""
    return {
        "items": [
            {
                "metadata": {
                    "name": "default",
                    "labels": {"kubernetes.io/metadata.name": "default"},
                    "annotations": {},
                    "creationTimestamp": "2023-01-01T00:00:00Z",
                },
                "status": {"phase": "Active"},
            },
            {
                "metadata": {
                    "name": "kube-system",
                    "labels": {"kubernetes.io/metadata.name": "kube-system"},
                    "annotations": {"meta": "system"},
                    "creationTimestamp": "2023-01-01T00:00:00Z",
                },
                "status": {"phase": "Active"},
            },
        ]
    }


class TestNamespaceUtilsFunction:
    """Test namespace utilities function."""

    def test_init(self, namespace_function):
        """Test function initialization."""
        assert namespace_function.name == "namespace_utils"
        assert "namespace" in namespace_function.description.lower()

    def test_get_schema(self, namespace_function):
        """Test schema definition."""
        schema = namespace_function.get_schema()
        assert schema["type"] == "object"

        properties = schema["properties"]
        assert "operation" in properties
        assert "all_namespaces" in properties
        assert "namespace_selector" in properties
        assert "namespace_names" in properties  # The actual parameter name
        assert "resource_types" in properties

        # Check operation enum
        assert "list" in properties["operation"]["enum"]
        assert "get" in properties["operation"]["enum"]
        assert "list-resources" in properties["operation"]["enum"]

    @pytest.mark.asyncio
    async def test_execute_no_clusters(self, namespace_function):
        """Test execution when no clusters are found."""
        with patch.object(namespace_function, "_discover_clusters", return_value=[]):
            result = await namespace_function.execute()

            assert result["status"] == "error"
            assert "No clusters discovered" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_list_operation(self, namespace_function, mock_clusters):
        """Test list operation."""
        mock_cluster_result = {
            "status": "success",
            "cluster": "cluster1",
            "namespaces": [
                {"name": "default", "status": "Active"},
                {"name": "kube-system", "status": "Active"},
            ],
            "namespace_count": 2,
        }

        with patch.object(
            namespace_function, "_discover_clusters", return_value=mock_clusters
        ):
            with patch.object(
                namespace_function,
                "_execute_namespace_operation",
                return_value=mock_cluster_result,
            ):
                result = await namespace_function.execute(operation="list")

                assert result["status"] == "success"
                assert result["details"]["operation"] == "list"
                assert result["details"]["clusters_total"] == 2
                assert result["details"]["clusters_succeeded"] == 2

    @pytest.mark.asyncio
    async def test_list_namespaces(
        self, namespace_function, mock_clusters, mock_namespace_json
    ):
        """Test namespace listing."""
        mock_result = {
            "returncode": 0,
            "stdout": json.dumps(mock_namespace_json),
            "stderr": "",
        }

        with patch.object(namespace_function, "_run_command", return_value=mock_result):
            result = await namespace_function._list_namespaces(
                mock_clusters[0], None, False, "", False, None, "", "", ""
            )

            assert result["status"] == "success"
            assert result["namespace_count"] == 2
            assert len(result["namespaces"]) == 2
            assert result["namespaces"][0]["name"] == "default"
            assert result["namespaces"][1]["name"] == "kube-system"

    @pytest.mark.asyncio
    async def test_list_namespaces_with_filter(
        self, namespace_function, mock_clusters, mock_namespace_json
    ):
        """Test namespace listing with name filter."""
        mock_result = {
            "returncode": 0,
            "stdout": json.dumps(mock_namespace_json),
            "stderr": "",
        }

        with patch.object(namespace_function, "_run_command", return_value=mock_result):
            result = await namespace_function._list_namespaces(
                mock_clusters[0], ["default"], False, "", False, None, "", "", ""
            )

            assert result["status"] == "success"
            assert result["namespace_count"] == 1
            assert result["namespaces"][0]["name"] == "default"

    @pytest.mark.asyncio
    async def test_get_namespace_details(self, namespace_function, mock_clusters):
        """Test getting detailed namespace information."""
        mock_namespace_detail = {
            "metadata": {
                "name": "default",
                "labels": {"kubernetes.io/metadata.name": "default"},
                "annotations": {},
                "creationTimestamp": "2023-01-01T00:00:00Z",
            },
            "status": {"phase": "Active"},
        }

        mock_result = {
            "returncode": 0,
            "stdout": json.dumps(mock_namespace_detail),
            "stderr": "",
        }

        with patch.object(namespace_function, "_run_command", return_value=mock_result):
            with patch.object(
                namespace_function, "_get_resource_quotas", return_value=[]
            ):
                with patch.object(
                    namespace_function, "_get_limit_ranges", return_value=[]
                ):
                    result = await namespace_function._get_namespace_details(
                        mock_clusters[0], ["default"], ""
                    )

                    assert result["status"] == "success"
                    assert len(result["namespace_details"]) == 1
                    assert result["namespace_details"][0]["name"] == "default"
                    assert result["namespace_details"][0]["status"] == "Active"

    @pytest.mark.asyncio
    async def test_list_namespace_resources(self, namespace_function, mock_clusters):
        """Test listing resources within namespaces."""
        mock_namespace_result = {
            "status": "success",
            "namespaces": [{"name": "default"}, {"name": "kube-system"}],
        }

        mock_resources = [
            {
                "name": "test-pod",
                "kind": "Pod",
                "api_version": "v1",
                "namespace": "default",
                "cluster": "cluster1",
                "labels": {},
                "annotations": {},
                "created": "2023-01-01T00:00:00Z",
            }
        ]

        with patch.object(
            namespace_function, "_list_namespaces", return_value=mock_namespace_result
        ):
            with patch.object(
                namespace_function,
                "_get_namespace_resources",
                return_value=mock_resources,
            ):
                result = await namespace_function._list_namespace_resources(
                    mock_clusters[0], None, True, None, "", "", ""
                )

                assert result["status"] == "success"
                assert result["resource_count"] == 2  # One resource per namespace
                assert len(result["resources"]) == 2

    @pytest.mark.asyncio
    async def test_get_namespace_resources(self, namespace_function, mock_clusters):
        """Test getting resources from a specific namespace."""
        mock_pod_json = {
            "items": [
                {
                    "metadata": {
                        "name": "test-pod",
                        "labels": {"app": "test"},
                        "annotations": {},
                        "creationTimestamp": "2023-01-01T00:00:00Z",
                    },
                    "kind": "Pod",
                    "apiVersion": "v1",
                }
            ]
        }

        mock_result = {
            "returncode": 0,
            "stdout": json.dumps(mock_pod_json),
            "stderr": "",
        }

        # Mock successful response for pods, empty for other resources
        def mock_run_command(cmd):
            if "pods" in cmd:
                return mock_result
            else:
                return {"returncode": 0, "stdout": '{"items": []}', "stderr": ""}

        with patch.object(
            namespace_function, "_run_command", side_effect=mock_run_command
        ):
            resources = await namespace_function._get_namespace_resources(
                mock_clusters[0], "default", ["pods"], "", "", ""
            )

            assert len(resources) == 1
            assert resources[0]["name"] == "test-pod"
            assert resources[0]["kind"] == "Pod"
            assert resources[0]["namespace"] == "default"

    @pytest.mark.asyncio
    async def test_get_resource_quotas(self, namespace_function, mock_clusters):
        """Test getting resource quotas for a namespace."""
        mock_quota_json = {
            "items": [
                {
                    "metadata": {"name": "compute-quota"},
                    "spec": {"hard": {"requests.cpu": "4", "requests.memory": "8Gi"}},
                }
            ]
        }

        mock_result = {
            "returncode": 0,
            "stdout": json.dumps(mock_quota_json),
            "stderr": "",
        }

        with patch.object(namespace_function, "_run_command", return_value=mock_result):
            quotas = await namespace_function._get_resource_quotas(
                mock_clusters[0], "default", ""
            )

            assert len(quotas) == 1
            assert quotas[0]["metadata"]["name"] == "compute-quota"

    @pytest.mark.asyncio
    async def test_get_limit_ranges(self, namespace_function, mock_clusters):
        """Test getting limit ranges for a namespace."""
        mock_limit_json = {
            "items": [
                {
                    "metadata": {"name": "mem-limit-range"},
                    "spec": {
                        "limits": [
                            {"default": {"memory": "512Mi"}, "type": "Container"}
                        ]
                    },
                }
            ]
        }

        mock_result = {
            "returncode": 0,
            "stdout": json.dumps(mock_limit_json),
            "stderr": "",
        }

        with patch.object(namespace_function, "_run_command", return_value=mock_result):
            limits = await namespace_function._get_limit_ranges(
                mock_clusters[0], "default", ""
            )

            assert len(limits) == 1
            assert limits[0]["metadata"]["name"] == "mem-limit-range"

    @pytest.mark.asyncio
    async def test_unsupported_operation(self, namespace_function, mock_clusters):
        """Test handling of unsupported operations."""
        with patch.object(
            namespace_function, "_discover_clusters", return_value=mock_clusters
        ):
            result = await namespace_function.execute(operation="invalid")

            # The operation should fail when no clusters succeed
            assert result["status"] == "error" or result["clusters_succeeded"] == 0
            assert (
                result["details"]["clusters_failed"] == 2
            )  # Both clusters should fail with unsupported operation

    @pytest.mark.asyncio
    async def test_execute_namespace_operation_error(
        self, namespace_function, mock_clusters
    ):
        """Test error handling in namespace operations."""
        result = await namespace_function._execute_namespace_operation(
            mock_clusters[0], "invalid", None, False, "", "", None, False, "", "", "table"
        )

        assert result["status"] == "error"
        assert "Unsupported operation" in result["error"]

    @pytest.mark.asyncio
    async def test_discover_clusters_with_kubeconfig(self, namespace_function):
        """Test cluster discovery with custom kubeconfig."""
        mock_contexts_output = "cluster1\ncluster2"
        mock_contexts_result = {
            "returncode": 0,
            "stdout": mock_contexts_output,
            "stderr": "",
        }

        mock_cluster_info_result = {
            "returncode": 0,
            "stdout": "Cluster info",
            "stderr": "",
        }

        with patch.object(namespace_function, "_run_command") as mock_run:

            def side_effect(cmd):
                # Verify kubeconfig is passed to commands
                if "get-contexts" in cmd:
                    assert "--kubeconfig" in cmd
                    assert "/path/to/kubeconfig" in cmd
                    return mock_contexts_result
                else:
                    assert "--kubeconfig" in cmd
                    return mock_cluster_info_result

            mock_run.side_effect = side_effect

            clusters = await namespace_function._discover_clusters(
                "/path/to/kubeconfig", ""
            )

            assert len(clusters) == 2
            assert clusters[0]["name"] == "cluster1"
            assert clusters[1]["name"] == "cluster2"
