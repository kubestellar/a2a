"""Kubeconfig function implementation."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.shared.base_functions import BaseFunction

# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #


@dataclass
class KubeconfigInput:
    """Parameters accepted by get_kubeconfig.execute."""

    kubeconfig_path: Optional[str] = None
    context: Optional[str] = None
    detail_level: str = "summary"


@dataclass
class KubeconfigOutput:
    """Uniform envelope returned by get_kubeconfig."""

    status: str
    details: Dict[str, Any] = field(default_factory=dict)


class KubeconfigFunction(BaseFunction):
    """Function to get details from kubeconfig file."""

    def __init__(self):
        super().__init__(
            name="get_kubeconfig",
            description="Get comprehensive details from kubeconfig file including available contexts, clusters, and users. Use this to understand your Kubernetes setup and available clusters for multi-cluster operations.",
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute the kubeconfig function.

        Args:
            kubeconfig_path: Path to kubeconfig file (defaults to ~/.kube/config)
            context: Specific context to get details for (optional)
            detail_level: Level of detail - 'summary', 'full', or 'contexts'

        Returns:
            Dictionary containing kubeconfig details
        """

        params = KubeconfigInput(**kwargs)
        kubeconfig_path = params.kubeconfig_path
        context = params.context
        detail_level = params.detail_level

        # Determine kubeconfig path
        if not kubeconfig_path:
            kubeconfig_path = os.environ.get("KUBECONFIG")
            if not kubeconfig_path:
                kubeconfig_path = str(Path.home() / ".kube" / "config")

        # Check if file exists
        if not os.path.exists(kubeconfig_path):
            err = {
                "error": f"Kubeconfig file not found at: {kubeconfig_path}",
                "suggestion": "Please ensure kubectl is configured or specify a valid kubeconfig path",
            }
            out = KubeconfigOutput(status="error", details=err)
            # Back-compat: expose detail keys at top level, too
            return {"status": out.status, **out.details}

        try:
            # Load kubeconfig
            with open(kubeconfig_path, "r") as f:
                kubeconfig = yaml.safe_load(f)

            result = {
                "kubeconfig_path": kubeconfig_path,
                "current_context": kubeconfig.get("current-context", "Not set"),
            }

            # Get contexts
            contexts = kubeconfig.get("contexts", [])
            result["contexts"] = [ctx["name"] for ctx in contexts]
            result["total_contexts"] = len(contexts)

            # If specific context requested
            if context:
                context_data = next(
                    (ctx for ctx in contexts if ctx["name"] == context), None
                )
                if context_data:
                    result["selected_context"] = self._get_context_details(
                        kubeconfig, context_data
                    )
                else:
                    result["error"] = f"Context '{context}' not found"

            # Add details based on level
            if detail_level == "full":
                result["clusters"] = self._get_clusters(kubeconfig)
                result["users"] = self._get_users(kubeconfig)
            elif detail_level == "contexts":
                result["context_details"] = [
                    self._get_context_details(kubeconfig, ctx) for ctx in contexts
                ]

            out = KubeconfigOutput(status="success", details=result)
            return {"status": out.status, **out.details}

        except Exception as e:
            err = {
                "error": f"Failed to parse kubeconfig: {str(e)}",
                "kubeconfig_path": kubeconfig_path,
            }
            out = KubeconfigOutput(status="error", details=err)
            return {"status": out.status, **out.details}

    def _get_context_details(self, kubeconfig: Dict, context: Dict) -> Dict[str, Any]:
        """Get details for a specific context."""
        context_info = context.get("context", {})
        return {
            "name": context["name"],
            "cluster": context_info.get("cluster"),
            "user": context_info.get("user"),
            "namespace": context_info.get("namespace", "default"),
        }

    def _get_clusters(self, kubeconfig: Dict) -> List[Dict[str, Any]]:
        """Get cluster information."""
        clusters = []
        for cluster in kubeconfig.get("clusters", []):
            cluster_data = cluster.get("cluster", {})
            clusters.append(
                {
                    "name": cluster["name"],
                    "server": cluster_data.get("server"),
                    "insecure_skip_tls_verify": cluster_data.get(
                        "insecure-skip-tls-verify", False
                    ),
                }
            )
        return clusters

    def _get_users(self, kubeconfig: Dict) -> List[Dict[str, Any]]:
        """Get user information (sanitized)."""
        users = []
        for user in kubeconfig.get("users", []):
            user_data = user.get("user", {})
            user_info = {"name": user["name"], "auth_type": []}

            # Determine auth type without exposing sensitive data
            if (
                "client-certificate" in user_data
                or "client-certificate-data" in user_data
            ):
                user_info["auth_type"].append("certificate")
            if "token" in user_data:
                user_info["auth_type"].append("token")
            if "exec" in user_data:
                user_info["auth_type"].append("exec")
                user_info["exec_command"] = user_data["exec"].get("command", "Unknown")

            users.append(user_info)
        return users

    def get_schema(self) -> Dict[str, Any]:
        """Return JSON schema for function parameters."""
        return {
            "type": "object",
            "properties": {
                "kubeconfig_path": {
                    "type": "string",
                    "description": "Path to kubeconfig file (defaults to ~/.kube/config or $KUBECONFIG)",
                },
                "context": {
                    "type": "string",
                    "description": "Specific context to get details for",
                },
                "detail_level": {
                    "type": "string",
                    "enum": ["summary", "full", "contexts"],
                    "description": "Level of detail to return",
                    "default": "summary",
                },
            },
            "required": [],
        }
