"""Function implementations."""

from src.shared.base_functions import function_registry
from src.shared.functions.binding_policy_management import BindingPolicyManagement
from src.shared.functions.deploy_to import DeployToFunction
from src.shared.functions.describe_resource import DescribeResourceFunction
from src.shared.functions.edit_resource import EditResourceFunction
from src.shared.functions.get_cluster_labels import GetClusterLabelsFunction
from src.shared.functions.gvrc_discovery import GVRCDiscoveryFunction
from src.shared.functions.helm.list import HelmListFunction
from src.shared.functions.helm.repo import HelmRepoFunction
from src.shared.functions.helm_deploy import HelmDeployFunction
from src.shared.functions.kubeconfig import KubeconfigFunction
from src.shared.functions.kubestellar_management import KubeStellarManagementFunction
from src.shared.functions.multicluster_create import MultiClusterCreateFunction
from src.shared.functions.multicluster_logs import MultiClusterLogsFunction
from src.shared.functions.namespace_utils import NamespaceUtilsFunction
from src.shared.functions.check_cluster_upgrades import CheckClusterUpgradesFunction


def initialize_functions():
    """Initialize and register all available functions."""
    # Register kubeconfig function
    function_registry.register(KubeconfigFunction())

    # Register enhanced KubeStellar management function
    function_registry.register(KubeStellarManagementFunction())

    # Register KubeStellar multi-cluster functions
    function_registry.register(MultiClusterCreateFunction())
    function_registry.register(MultiClusterLogsFunction())
    function_registry.register(DeployToFunction())

    # Register Helm functions
    function_registry.register(HelmRepoFunction())
    function_registry.register(HelmListFunction())

    function_registry.register(EditResourceFunction())
    function_registry.register(DescribeResourceFunction())

    function_registry.register(BindingPolicyManagement())

    # Register Helm deployment function
    function_registry.register(HelmDeployFunction())
    
    # Register cluster labels helper function
    function_registry.register(GetClusterLabelsFunction())

    # Register GVRC and namespace utilities
    function_registry.register(GVRCDiscoveryFunction())
    function_registry.register(NamespaceUtilsFunction())

    # Register cluster upgrade check function
    function_registry.register(CheckClusterUpgradesFunction())

    # Add more function registrations here as they are created
