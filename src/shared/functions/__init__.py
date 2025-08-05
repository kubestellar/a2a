"""Function implementations."""

from ..base_functions import function_registry
from .deploy_to import DeployToFunction
from .gvrc_discovery import GVRCDiscoveryFunction
from .kubeconfig import KubeconfigFunction
from .kubestellar_management import KubeStellarManagementFunction
from .multicluster_create import MultiClusterCreateFunction
from .multicluster_logs import MultiClusterLogsFunction
from .namespace_utils import NamespaceUtilsFunction


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

    # Register GVRC and namespace utilities
    function_registry.register(GVRCDiscoveryFunction())
    function_registry.register(NamespaceUtilsFunction())

    # Add more function registrations here as they are created
