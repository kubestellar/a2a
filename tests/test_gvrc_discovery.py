"""Tests for GVRC discovery functionality."""

from unittest.mock import patch

import pytest

from src.shared.functions.gvrc_discovery import GVRCDiscoveryFunction


@pytest.fixture
def gvrc_function():
    """Create a GVRC discovery function instance."""
    return GVRCDiscoveryFunction()


@pytest.fixture
def mock_clusters():
    """Mock cluster data."""
    return [
        {"name": "cluster1", "context": "cluster1", "status": "Ready"},
        {"name": "cluster2", "context": "cluster2", "status": "Ready"},
    ]


class TestGVRCDiscoveryFunction:
    """Test GVRC discovery function."""

    def test_init(self, gvrc_function):
        """Test function initialization."""
        assert gvrc_function.name == "gvrc_discovery"
        assert "resources" in gvrc_function.description.lower()
        assert "gvrc" in gvrc_function.description.lower()

    def test_get_schema(self, gvrc_function):
        """Test schema definition."""
        schema = gvrc_function.get_schema()
        assert schema["type"] == "object"

        properties = schema["properties"]
        assert "resource_filter" in properties
        assert "all_namespaces" in properties
        assert "api_resources" in properties
        assert "custom_resources" in properties
        assert "output_format" in properties

        # Check default values
        assert properties["all_namespaces"]["default"] is False
        assert properties["api_resources"]["default"] is True
        assert properties["output_format"]["default"] == "summary"

    @pytest.mark.asyncio
    async def test_execute_no_clusters(self, gvrc_function):
        """Test execution when no clusters are found."""
        with patch.object(gvrc_function, "_discover_clusters", return_value=[]):
            result = await gvrc_function.execute()

            assert result["status"] == "error"
            assert "No clusters discovered" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_successful_discovery(self, gvrc_function, mock_clusters):
        """Test successful GVRC discovery."""
        mock_cluster_result = {
            "status": "success",
            "cluster": "cluster1",
            "resources": [
                {
                    "name": "pods",
                    "shortnames": ["po"],
                    "api_version": "v1",
                    "kind": "Pod",
                    "namespaced": True,
                    "categories": ["all"],
                }
            ],
            "namespaces": [],
            "resource_count": 1,
            "namespace_count": 0,
        }

        with patch.object(
            gvrc_function, "_discover_clusters", return_value=mock_clusters
        ):
            with patch.object(
                gvrc_function,
                "_discover_cluster_gvrc",
                return_value=mock_cluster_result,
            ):
                result = await gvrc_function.execute(api_resources=True)

                assert result["status"] == "success"
                assert result["clusters_total"] == 2
                assert result["clusters_succeeded"] == 2
                assert "discovery_results" in result

    @pytest.mark.asyncio
    async def test_get_api_resources(self, gvrc_function, mock_clusters):
        """Test API resources discovery."""
        mock_kubectl_output = """NAME                              SHORTNAMES   APIVERSION                        NAMESPACED   KIND                             CATEGORIES
pods                              po           v1                                true         Pod                              all
services                          svc          v1                                true         Service                          all
deployments                       deploy       apps/v1                           true         Deployment                       all"""

        mock_result = {"returncode": 0, "stdout": mock_kubectl_output, "stderr": ""}

        with patch.object(gvrc_function, "_run_command", return_value=mock_result):
            resources = await gvrc_function._get_api_resources(
                mock_clusters[0], "", None, ""
            )

            assert len(resources) == 3
            assert resources[0]["name"] == "pods"
            assert resources[0]["shortnames"] == ["po"]
            assert resources[0]["api_version"] == "v1"
            assert resources[0]["namespaced"] is True
            assert resources[0]["categories"] == ["all"]

    @pytest.mark.asyncio
    async def test_get_namespaces(self, gvrc_function, mock_clusters):
        """Test namespace discovery."""
        mock_kubectl_output = """NAME              STATUS   AGE
default           Active   10d
kube-system       Active   10d
kube-public       Active   10d"""

        mock_result = {"returncode": 0, "stdout": mock_kubectl_output, "stderr": ""}

        with patch.object(gvrc_function, "_run_command", return_value=mock_result):
            with patch.object(
                gvrc_function,
                "_get_namespace_details",
                return_value={"labels": {}, "annotations": {}},
            ):
                namespaces = await gvrc_function._get_namespaces(
                    mock_clusters[0], "", ""
                )

                assert len(namespaces) == 3
                assert namespaces[0]["name"] == "default"
                assert namespaces[0]["status"] == "Active"

    def test_create_summary(self, gvrc_function):
        """Test summary creation."""
        mock_results = {
            "cluster1": {
                "status": "success",
                "resources": [
                    {"name": "pods", "categories": ["all"]},
                    {"name": "services", "categories": ["all", "core"]},
                ],
                "namespaces": [{"name": "default"}, {"name": "kube-system"}],
            },
            "cluster2": {
                "status": "success",
                "resources": [
                    {"name": "pods", "categories": ["all"]},
                    {"name": "deployments", "categories": ["all", "apps"]},
                ],
                "namespaces": [{"name": "default"}],
            },
        }

        summary = gvrc_function._create_summary(mock_results)

        assert summary["total_resources"] == 4
        assert summary["total_namespaces"] == 3
        assert "all" in summary["resource_categories"]
        assert "core" in summary["resource_categories"]
        assert "apps" in summary["resource_categories"]
        assert "pods" in summary["common_resources"]
        assert summary["namespace_distribution"]["cluster1"] == 2
        assert summary["namespace_distribution"]["cluster2"] == 1

    @pytest.mark.asyncio
    async def test_resource_filtering(self, gvrc_function, mock_clusters):
        """Test resource filtering functionality."""
        mock_kubectl_output = """NAME                              SHORTNAMES   APIVERSION                        NAMESPACED   KIND                             CATEGORIES
pods                              po           v1                                true         Pod                              all
services                          svc          v1                                true         Service                          all
deployments                       deploy       apps/v1                           true         Deployment                       all"""

        mock_result = {"returncode": 0, "stdout": mock_kubectl_output, "stderr": ""}

        with patch.object(gvrc_function, "_run_command", return_value=mock_result):
            # Test with resource filter
            resources = await gvrc_function._get_api_resources(
                mock_clusters[0], "pod", None, ""
            )

            assert len(resources) == 1
            assert resources[0]["name"] == "pods"

            # Test with category filter
            resources = await gvrc_function._get_api_resources(
                mock_clusters[0], "", ["all"], ""
            )

            assert len(resources) == 3  # All resources have 'all' category

    @pytest.mark.asyncio
    async def test_discover_clusters_filters_wds(self, gvrc_function):
        """Test that WDS clusters are filtered out."""
        mock_contexts_output = "cluster1\nwds-cluster\ncluster2\nmy-wds-cluster"

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

        with patch.object(gvrc_function, "_run_command") as mock_run:

            def side_effect(cmd):
                if "get-contexts" in cmd:
                    return mock_contexts_result
                else:
                    return mock_cluster_info_result

            mock_run.side_effect = side_effect

            clusters = await gvrc_function._discover_clusters("", "")

            # Should exclude WDS clusters
            cluster_names = [c["name"] for c in clusters]
            assert "cluster1" in cluster_names
            assert "cluster2" in cluster_names
            assert "wds-cluster" not in cluster_names
            assert "my-wds-cluster" not in cluster_names

    def test_is_wds_cluster(self, gvrc_function):
        """Test WDS cluster detection."""
        assert gvrc_function._is_wds_cluster("wds-cluster") is True
        assert gvrc_function._is_wds_cluster("my-wds-cluster") is True
        assert gvrc_function._is_wds_cluster("cluster-wds-prod") is True
        assert gvrc_function._is_wds_cluster("regular-cluster") is False
        assert gvrc_function._is_wds_cluster("cluster1") is False
