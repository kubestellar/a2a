"""Function implementations."""

from src.shared.base_functions import function_registry
from src.shared.functions.cluster_label_management import ClusterLabelManagement
from src.shared.functions.deploy_to import DeployToFunction
from src.shared.functions.gvrc_discovery import GVRCDiscoveryFunction
from src.shared.functions.helm_deploy import HelmDeployFunction
from src.shared.functions.kubeconfig import KubeconfigFunction
from src.shared.functions.kubestellar_management import KubeStellarManagementFunction
from src.shared.functions.multicluster_create import MultiClusterCreateFunction
from src.shared.functions.multicluster_logs import MultiClusterLogsFunction
from src.shared.functions.namespace_utils import NamespaceUtilsFunction


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

    # Register Helm deployment function
    function_registry.register(HelmDeployFunction())
    
    # Register cluster labels helper function
    function_registry.register(ClusterLabelManagement())

    # Register GVRC and namespace utilities
    function_registry.register(GVRCDiscoveryFunction())
    function_registry.register(NamespaceUtilsFunction())

    # Add more function registrations here as they are created
