"""Function implementations."""

from ..base_functions import function_registry
from .deploy_to import DeployToFunction
from .get_cluster_labels import GetClusterLabelsFunction
from .gvrc_discovery import GVRCDiscoveryFunction
from .helm_deploy import HelmDeployFunction
from .kubeconfig import KubeconfigFunction
from .kubestellar_management import KubeStellarManagementFunction
from .kubestellar_setup import KubeStellarSetupFunction
from .multicluster_create import MultiClusterCreateFunction
from .multicluster_logs import MultiClusterLogsFunction
from .namespace_utils import NamespaceUtilsFunction


def initialize_functions():
    """Initialize and register all available functions."""
    # Register kubeconfig function
    function_registry.register(KubeconfigFunction())

    # Register enhanced KubeStellar management function
    function_registry.register(KubeStellarManagementFunction())
    
    # Register KubeStellar setup function
    function_registry.register(KubeStellarSetupFunction())

    # Register KubeStellar multi-cluster functions
    function_registry.register(MultiClusterCreateFunction())
    function_registry.register(MultiClusterLogsFunction())
    function_registry.register(DeployToFunction())

    # Register Helm deployment function
    function_registry.register(HelmDeployFunction())
    
    # Register cluster labels helper function
    function_registry.register(GetClusterLabelsFunction())

    # Register GVRC and namespace utilities
    function_registry.register(GVRCDiscoveryFunction())
    function_registry.register(NamespaceUtilsFunction())

    # Add more function registrations here as they are created
