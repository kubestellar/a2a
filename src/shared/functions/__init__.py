"""Function implementations."""

from typing import Dict, List, Type

from src.shared.base_functions import BaseFunction, function_registry
from src.shared.providers import ProviderMode

from src.shared.functions.binding_policy_management import BindingPolicyManagement
from src.shared.functions.check_cluster_upgrades import CheckClusterUpgradesFunction
from src.shared.functions.cluster_management import ClusterManagementFunction
from src.shared.functions.deploy_to import DeployToFunction
from src.shared.functions.describe_resource import DescribeResourceFunction
from src.shared.functions.edit_resource import EditResourceFunction
from src.shared.functions.fetch_manifest import FetchManifestFunction
from src.shared.functions.gvrc_discovery import GVRCDiscoveryFunction
from src.shared.functions.helm.install import HelmInstallFunction
from src.shared.functions.helm.list import HelmListFunction
from src.shared.functions.helm.repo import HelmRepoFunction
from src.shared.functions.helm_deploy import HelmDeployFunction
from src.shared.functions.kubeconfig import KubeconfigFunction
from src.shared.functions.kubestellar_management import KubeStellarManagementFunction
from src.shared.functions.multicluster_create import MultiClusterCreateFunction
from src.shared.functions.multicluster_logs import MultiClusterLogsFunction
from src.shared.functions.namespace_utils import NamespaceUtilsFunction


def _function_sets() -> Dict[ProviderMode, List[Type[BaseFunction]]]:
    base: List[Type[BaseFunction]] = [
        KubeconfigFunction,
        FetchManifestFunction,
        DescribeResourceFunction,
        EditResourceFunction,
        NamespaceUtilsFunction,
        GVRCDiscoveryFunction,
        CheckClusterUpgradesFunction,
        HelmRepoFunction,
        HelmListFunction,
        HelmInstallFunction,
        HelmDeployFunction,
    ]

    kubernetes_extras: List[Type[BaseFunction]] = [
        DeployToFunction,
        ClusterManagementFunction,
    ]

    kubestellar = (
        base
        + kubernetes_extras
        + [
            KubeStellarManagementFunction,
            MultiClusterCreateFunction,
            MultiClusterLogsFunction,
            BindingPolicyManagement,
        ]
    )

    return {
        ProviderMode.KUBERNETES: base + kubernetes_extras,
        ProviderMode.KUBESTELLAR: kubestellar,
    }


def initialize_functions(mode: ProviderMode) -> None:
    """Initialize and register functions based on provider mode."""

    function_registry.reset()
    for func_cls in _function_sets()[mode]:
        function_registry.register(func_cls())
