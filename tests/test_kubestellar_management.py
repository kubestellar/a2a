"""Tests for KubeStellar management function."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.shared.functions.kubestellar_management import KubeStellarManagementFunction


class TestKubeStellarManagementFunction:
    """Test cases for KubeStellar management function."""

    @pytest.fixture
    def kubestellar_function(self):
        """Create KubeStellar management function instance."""
        return KubeStellarManagementFunction()

    def test_init(self, kubestellar_function):
        """Test function initialization."""
        assert kubestellar_function.name == "kubestellar_management"
        assert "kubestellar" in kubestellar_function.description.lower()
        assert "binding" in kubestellar_function.description.lower()
        assert "deep search" in kubestellar_function.description.lower()

    def test_get_schema(self, kubestellar_function):
        """Test schema definition."""
        schema = kubestellar_function.get_schema()

        assert schema["type"] == "object"
        assert "operation" in schema["properties"]
        assert "binding_policies" in schema["properties"]
        assert "work_statuses" in schema["properties"]
        assert "deep_analysis" in schema["properties"]

        # Check operation enum values
        operation_enum = schema["properties"]["operation"]["enum"]
        assert "deep_search" in operation_enum
        assert "policy_analysis" in operation_enum
        assert "resource_inventory" in operation_enum
        assert "topology_map" in operation_enum

    @pytest.mark.asyncio
    async def test_execute_no_clusters(self, kubestellar_function):
        """Test execution when no clusters are discovered."""
        with patch.object(
            kubestellar_function,
            "_discover_kubestellar_topology",
            new_callable=AsyncMock,
        ) as mock_discover:
            mock_discover.return_value = []

            result = await kubestellar_function.execute()

            assert result["status"] == "error"
            assert "no kubestellar clusters discovered" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_topology_map_operation(self, kubestellar_function):
        """Test topology map operation."""
        mock_clusters = [
            {
                "name": "wds-test",
                "type": "wds",
                "context": "wds-test",
                "kubestellar_info": {"api_resources": ["bindingpolicies"]},
            },
            {
                "name": "its-test",
                "type": "its",
                "context": "its-test",
                "kubestellar_info": {"api_resources": ["workstatuses"]},
            },
            {
                "name": "wec-test",
                "type": "wec",
                "context": "wec-test",
                "kubestellar_info": {"api_resources": ["pods"]},
            },
        ]

        with patch.object(
            kubestellar_function,
            "_discover_kubestellar_topology",
            new_callable=AsyncMock,
        ) as mock_discover:
            mock_discover.return_value = mock_clusters

            result = await kubestellar_function.execute(operation="topology_map")

            assert result["status"] == "success"
            assert result["operation"] == "topology_map"
            assert len(result["wds_clusters"]) == 1
            assert len(result["wec_clusters"]) == 1
            assert result["wds_clusters"][0]["name"] == "wds-test"
            assert result["wec_clusters"][0]["name"] == "wec-test"

    @pytest.mark.asyncio
    async def test_deep_search_operation(self, kubestellar_function):
        """Test deep search operation."""
        mock_clusters = [
            {
                "name": "cluster1",
                "type": "wec",
                "context": "cluster1",
                "kubestellar_info": {},
            }
        ]

        # Mock the deep search cluster method
        mock_cluster_result = {
            "cluster": "cluster1",
            "cluster_type": "wec",
            "status": "success",
            "namespaces": {
                "default": [
                    {
                        "name": "test-pod",
                        "kind": "Pod",
                        "api_version": "v1",
                        "namespace": "default",
                        "cluster": "cluster1",
                        "labels": {},
                        "annotations": {},
                        "created": "2024-01-01T00:00:00Z",
                    }
                ]
            },
            "resources_by_type": {"pod": [{"name": "test-pod", "kind": "Pod"}]},
            "total_resources": 1,
            "kubestellar_resources": [],
        }

        with (
            patch.object(
                kubestellar_function,
                "_discover_kubestellar_topology",
                new_callable=AsyncMock,
            ) as mock_discover,
            patch.object(
                kubestellar_function, "_deep_search_cluster", new_callable=AsyncMock
            ) as mock_deep_search,
            patch.object(
                kubestellar_function,
                "_aggregate_binding_policies",
                new_callable=AsyncMock,
            ) as mock_policies,
            patch.object(
                kubestellar_function, "_aggregate_work_statuses", new_callable=AsyncMock
            ) as mock_statuses,
        ):

            mock_discover.return_value = mock_clusters
            mock_deep_search.return_value = mock_cluster_result
            mock_policies.return_value = {
                "total_policies": 0,
                "policies_by_cluster": {},
            }
            mock_statuses.return_value = {
                "total_work_statuses": 0,
                "statuses_by_cluster": {},
            }

            result = await kubestellar_function.execute(operation="deep_search")

            assert result["status"] == "success"
            assert result["operation"] == "deep_search"
            assert result["clusters_analyzed"] == 1
            assert "resource_summary" in result
            assert result["cluster_results"]["cluster1"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_classify_kubestellar_space_wds(self, kubestellar_function):
        """Test WDS space classification."""
        mock_command_output = {
            "returncode": 0,
            "stdout": "bindingpolicies   control.kubestellar.io/v1alpha1   true   BindingPolicy",
        }

        with (
            patch.object(
                kubestellar_function, "_run_command", new_callable=AsyncMock
            ) as mock_run,
            patch.object(
                kubestellar_function,
                "_get_kubestellar_namespaces",
                new_callable=AsyncMock,
            ) as mock_ns,
            patch.object(
                kubestellar_function,
                "_get_kubestellar_api_resources",
                new_callable=AsyncMock,
            ) as mock_api,
        ):

            mock_run.return_value = mock_command_output
            mock_ns.return_value = ["kubestellar-system"]
            mock_api.return_value = ["bindingpolicies"]

            space_info = await kubestellar_function._classify_kubestellar_space(
                "wds-test", ""
            )

            assert space_info["type"] == "wds"
            assert space_info["name"] == "wds-test"
            assert space_info["kubestellar_components"]["binding_controller"] is True

    @pytest.mark.asyncio
    async def test_classify_kubestellar_space_its(self, kubestellar_function):
        """Test ITS space classification."""
        mock_command_output = {
            "returncode": 0,
            "stdout": "workstatuses   ws,wss   control.kubestellar.io/v1alpha1   true   WorkStatus",
        }

        with (
            patch.object(
                kubestellar_function, "_run_command", new_callable=AsyncMock
            ) as mock_run,
            patch.object(
                kubestellar_function,
                "_get_kubestellar_namespaces",
                new_callable=AsyncMock,
            ) as mock_ns,
            patch.object(
                kubestellar_function,
                "_get_kubestellar_api_resources",
                new_callable=AsyncMock,
            ) as mock_api,
        ):

            mock_run.return_value = mock_command_output
            mock_ns.return_value = ["open-cluster-management"]
            mock_api.return_value = ["workstatuses"]

            space_info = await kubestellar_function._classify_kubestellar_space(
                "its-test", ""
            )

            assert space_info["type"] == "its"
            assert space_info["kubestellar_components"]["transport_controller"] is True

    @pytest.mark.asyncio
    async def test_get_kubestellar_namespaces(self, kubestellar_function):
        """Test getting KubeStellar-related namespaces."""
        mock_namespaces_data = {
            "items": [
                {
                    "metadata": {
                        "name": "kubestellar-system",
                        "labels": {"kubestellar.io/managed": "true"},
                    }
                },
                {
                    "metadata": {
                        "name": "open-cluster-management",
                        "labels": {"open-cluster-management.io/managed": "true"},
                    }
                },
                {"metadata": {"name": "regular-namespace", "labels": {}}},
            ]
        }

        mock_command_output = {
            "returncode": 0,
            "stdout": json.dumps(mock_namespaces_data),
        }

        with patch.object(
            kubestellar_function, "_run_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = mock_command_output

            namespaces = await kubestellar_function._get_kubestellar_namespaces(
                "test-context", ""
            )

            assert "kubestellar-system" in namespaces
            assert "open-cluster-management" in namespaces
            assert "regular-namespace" not in namespaces

    @pytest.mark.asyncio
    async def test_get_kubestellar_api_resources(self, kubestellar_function):
        """Test getting KubeStellar API resources."""
        mock_outputs = [
            {
                "returncode": 0,
                "stdout": "NAME             SHORTNAMES   APIVERSION                        NAMESPACED   KIND\nbindingpolicies   bp           control.kubestellar.io/v1alpha1   true         BindingPolicy\nworkstatuses      ws           control.kubestellar.io/v1alpha1   true         WorkStatus",
            },
            {
                "returncode": 0,
                "stdout": "NAME             SHORTNAMES   APIVERSION                              NAMESPACED   KIND\nmanagedclusters               cluster.open-cluster-management.io/v1   false        ManagedCluster",
            },
            {
                "returncode": 0,
                "stdout": "NAME            SHORTNAMES   APIVERSION                        NAMESPACED   KIND\nmanifestworks                work.open-cluster-management.io/v1   true         ManifestWork",
            },
        ]

        with patch.object(
            kubestellar_function, "_run_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.side_effect = mock_outputs

            resources = await kubestellar_function._get_kubestellar_api_resources(
                "test-context", ""
            )

            assert "bindingpolicies" in resources
            assert "workstatuses" in resources
            assert "managedclusters" in resources
            assert "manifestworks" in resources

    @pytest.mark.asyncio
    async def test_search_namespace_resources(self, kubestellar_function):
        """Test searching resources in a namespace."""
        mock_cluster = {"name": "test-cluster", "context": "test-context"}
        mock_pod_data = {
            "items": [
                {
                    "metadata": {
                        "name": "test-pod",
                        "labels": {"app": "test"},
                        "annotations": {},
                        "creationTimestamp": "2024-01-01T00:00:00Z",
                        "uid": "test-uid",
                        "resourceVersion": "123",
                    },
                    "kind": "Pod",
                    "apiVersion": "v1",
                    "status": {"phase": "Running"},
                    "spec": {"nodeName": "test-node"},
                }
            ]
        }

        mock_command_output = {"returncode": 0, "stdout": json.dumps(mock_pod_data)}

        with patch.object(
            kubestellar_function, "_run_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = mock_command_output

            resources = await kubestellar_function._search_namespace_resources(
                mock_cluster, "default", ["pods"], "", "", ""
            )

            assert len(resources) == 1
            assert resources[0]["name"] == "test-pod"
            assert resources[0]["kind"] == "Pod"
            assert resources[0]["phase"] == "Running"
            assert resources[0]["node"] == "test-node"

    def test_is_kubestellar_resource(self, kubestellar_function):
        """Test KubeStellar resource identification."""
        # Test KubeStellar API resource
        ks_resource = {
            "api_version": "control.kubestellar.io/v1alpha1",
            "kind": "BindingPolicy",
            "labels": {},
            "annotations": {},
        }
        assert kubestellar_function._is_kubestellar_resource(ks_resource) is True

        # Test resource with KubeStellar labels
        labeled_resource = {
            "api_version": "v1",
            "kind": "Pod",
            "labels": {"kubestellar.io/managed": "true"},
            "annotations": {},
        }
        assert kubestellar_function._is_kubestellar_resource(labeled_resource) is True

        # Test resource with KubeStellar annotations
        annotated_resource = {
            "api_version": "v1",
            "kind": "Service",
            "labels": {},
            "annotations": {"kubestellar.io/binding-policy": "test-policy"},
        }
        assert kubestellar_function._is_kubestellar_resource(annotated_resource) is True

        # Test KubeStellar kind
        workstatus_resource = {
            "api_version": "v1",
            "kind": "WorkStatus",
            "labels": {},
            "annotations": {},
        }
        assert (
            kubestellar_function._is_kubestellar_resource(workstatus_resource) is True
        )

        # Test regular resource
        regular_resource = {
            "api_version": "v1",
            "kind": "Pod",
            "labels": {},
            "annotations": {},
        }
        assert kubestellar_function._is_kubestellar_resource(regular_resource) is False

    def test_aggregate_resource_summary(self, kubestellar_function):
        """Test resource summary aggregation."""
        cluster_results = {
            "cluster1": {
                "status": "success",
                "total_resources": 10,
                "cluster_type": "wec",
                "resources_by_type": {
                    "pod": [{"name": "pod1"}, {"name": "pod2"}],
                    "service": [{"name": "svc1"}],
                },
                "kubestellar_resources": [{"name": "ks1"}],
            },
            "cluster2": {
                "status": "success",
                "total_resources": 5,
                "cluster_type": "wds",
                "resources_by_type": {
                    "pod": [{"name": "pod3"}],
                    "bindingpolicy": [{"name": "bp1"}],
                },
                "kubestellar_resources": [{"name": "ks2"}, {"name": "ks3"}],
            },
        }

        summary = kubestellar_function._aggregate_resource_summary(cluster_results)

        assert summary["total_clusters"] == 2
        assert summary["total_resources"] == 15
        assert summary["resources_by_cluster"]["cluster1"] == 10
        assert summary["resources_by_cluster"]["cluster2"] == 5
        assert summary["resources_by_type"]["pod"] == 3
        assert summary["resources_by_type"]["service"] == 1
        assert summary["resources_by_type"]["bindingpolicy"] == 1
        assert summary["kubestellar_resources"] == 3
        assert summary["cluster_types"]["wec"]["count"] == 1
        assert summary["cluster_types"]["wds"]["count"] == 1

    @pytest.mark.asyncio
    async def test_analyze_resource_placement(self, kubestellar_function):
        """Test resource placement analysis."""
        cluster_results = {
            "cluster1": {
                "status": "success",
                "resources_by_type": {
                    "pod": [
                        {"name": "p1"},
                        {"name": "p2"},
                        {"name": "p3"},
                        {"name": "p4"},
                        {"name": "p5"},
                    ],  # 5 pods
                    "service": [{"name": "s1"}],  # 1 service
                },
            },
            "cluster2": {
                "status": "success",
                "resources_by_type": {
                    "pod": [
                        {"name": "p6"}
                    ],  # 1 pod - significant imbalance (5 vs 1, avg is 3, 5 > 3*1.5)
                    "service": [{"name": "s2"}],  # 1 service
                },
            },
        }

        analysis = kubestellar_function._analyze_resource_placement(cluster_results)

        assert "distribution_patterns" in analysis
        assert analysis["distribution_patterns"]["pod"]["cluster1"] == 5
        assert analysis["distribution_patterns"]["pod"]["cluster2"] == 1
        assert len(analysis["recommendations"]) > 0
        # Should recommend redistributing pods from cluster1 (5 > 3*1.5 = 4.5)

    @pytest.mark.asyncio
    async def test_create_dependency_map(self, kubestellar_function):
        """Test dependency map creation."""
        cluster_results = {
            "cluster1": {
                "status": "success",
                "namespaces": {
                    "default": [
                        {
                            "name": "managed-pod",
                            "kind": "Pod",
                            "annotations": {
                                "kubestellar.io/binding-policy": "test-policy"
                            },
                            "labels": {},
                        }
                    ]
                },
            }
        }

        dependency_map = kubestellar_function._create_dependency_map(cluster_results)

        assert "resource_relationships" in dependency_map
        assert "cross_cluster_references" in dependency_map
        # Check that KubeStellar-managed resources are identified
        resource_key = "cluster1/default/Pod/managed-pod"
        assert resource_key in dependency_map["resource_relationships"]

    @pytest.mark.asyncio
    async def test_run_command_success(self, kubestellar_function):
        """Test successful command execution."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"success output", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await kubestellar_function._run_command(["echo", "test"])

            assert result["returncode"] == 0
            assert result["stdout"] == "success output"
            assert result["stderr"] == ""

    @pytest.mark.asyncio
    async def test_run_command_failure(self, kubestellar_function):
        """Test command execution failure."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"error output")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            result = await kubestellar_function._run_command(["false"])

            assert result["returncode"] == 1
            assert result["stdout"] == ""
            assert result["stderr"] == "error output"

    @pytest.mark.asyncio
    async def test_run_command_exception(self, kubestellar_function):
        """Test command execution with exception."""
        with patch(
            "asyncio.create_subprocess_exec", side_effect=Exception("Command failed")
        ):
            result = await kubestellar_function._run_command(["nonexistent"])

            assert result["returncode"] == 1
            assert result["stdout"] == ""
            assert "Command failed" in result["stderr"]

    @pytest.mark.asyncio
    async def test_unsupported_operation(self, kubestellar_function):
        """Test unsupported operation handling."""
        mock_clusters = [{"name": "test", "type": "wec", "context": "test"}]

        with patch.object(
            kubestellar_function,
            "_discover_kubestellar_topology",
            new_callable=AsyncMock,
        ) as mock_discover:
            mock_discover.return_value = mock_clusters

            result = await kubestellar_function.execute(operation="invalid_operation")

            assert result["status"] == "error"
            assert "unsupported operation" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_exception_handling(self, kubestellar_function):
        """Test exception handling in execute method."""
        with patch.object(
            kubestellar_function,
            "_discover_kubestellar_topology",
            side_effect=Exception("Test error"),
        ):
            result = await kubestellar_function.execute()

            assert result["status"] == "error"
            assert (
                "failed to execute kubestellar management operation"
                in result["error"].lower()
            )
            assert "test error" in result["error"].lower()
