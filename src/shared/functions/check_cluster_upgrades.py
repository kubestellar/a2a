from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import aiohttp

from src.shared.base_functions import BaseFunction


@dataclass
class ClusterUpgradeStatus:
    """Represents the upgrade status of a single cluster."""

    cluster_name: str
    current_version: str
    latest_version: str
    upgrade_needed: bool
    error: Optional[str] = None


@dataclass
class CheckClusterUpgradesOutput:
    """Output for the check_cluster_upgrades function."""

    status: str
    clusters: List[ClusterUpgradeStatus] = field(default_factory=list)
    summary: str = ""


class CheckClusterUpgradesFunction(BaseFunction):
    """
    Checks for available Kubernetes version upgrades for all clusters.
    """

    def __init__(self):
        super().__init__(
            name="check_cluster_upgrades",
            description="Checks for available Kubernetes version upgrades for all clusters.",
        )

    async def execute(self, kubeconfig: str = "") -> Dict[str, Any]:
        """
        Checks for available Kubernetes version upgrades for all clusters.

        Args:
            kubeconfig: Path to the kubeconfig file.

        Returns:
            A dictionary with the upgrade status of each cluster.
        """
        try:
            latest_version = await self._get_latest_stable_k8s_version()
            if not latest_version:
                return {
                    "status": "error",
                    "error": "Could not fetch the latest stable Kubernetes version.",
                }

            clusters = await self._discover_clusters(kubeconfig)
            if not clusters:
                return CheckClusterUpgradesOutput(
                    status="success",
                    summary="No clusters discovered.",
                ).__dict__

            upgrade_statuses = await asyncio.gather(
                *[
                    self._get_cluster_upgrade_status(cluster, latest_version, kubeconfig)
                    for cluster in clusters
                ]
            )

            output = CheckClusterUpgradesOutput(
                status="success",
                clusters=[status for status in upgrade_statuses if status],
                summary=f"Compared against the latest stable Kubernetes version: {latest_version}",
            )

            return output.__dict__

        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _get_latest_stable_k8s_version(self) -> Optional[str]:
        """Fetches the latest stable Kubernetes version from Google's GCS bucket."""
        url = "https://storage.googleapis.com/kubernetes-release/release/stable.txt"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return (await response.text()).strip()
        except Exception:
            return None
        return None

    async def _discover_clusters(self, kubeconfig: str) -> List[Dict[str, Any]]:
        """Discover available clusters using kubectl."""
        cmd = ["kubectl", "config", "get-contexts", "-o", "json"]
        if kubeconfig:
            cmd.extend(["--kubeconfig", kubeconfig])

        result = await self._run_command(cmd)
        if result["returncode"] != 0:
            # Return an empty list but log the error or make it accessible for debugging
            print(f"Error discovering clusters: {result['stderr']}")
            return []

        try:
            contexts = json.loads(result["stdout"])["contexts"]
            return [
                {"name": context["name"], "context": context["name"]}
                for context in contexts
                if "wds" not in context["name"]
            ]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error parsing kubectl contexts: {e}")
            return []

    async def _get_cluster_upgrade_status(
        self, cluster: Dict[str, Any], latest_version: str, kubeconfig: str
    ) -> Optional[ClusterUpgradeStatus]:
        """Gets the upgrade status of a single cluster."""
        cmd = [
            "kubectl",
            "get",
            "nodes",
            "-o",
            "json",
            "--context",
            cluster["context"],
        ]
        if kubeconfig:
            cmd.extend(["--kubeconfig", kubeconfig])

        result = await self._run_command(cmd)
        if result["returncode"] != 0:
            return ClusterUpgradeStatus(
                cluster_name=cluster["name"],
                current_version="N/A",
                latest_version=latest_version,
                upgrade_needed=False,
                error=result["stderr"],
            )

        try:
            nodes = json.loads(result["stdout"])["items"]
            if not nodes:
                return ClusterUpgradeStatus(
                    cluster_name=cluster["name"],
                    current_version="N/A",
                    latest_version=latest_version,
                    upgrade_needed=False,
                    error="No nodes found in the cluster.",
                )

            # For simplicity, we'll use the version of the first node.
            # In a real-world scenario, you might want to check all nodes.
            kubelet_version = nodes[0]["status"]["nodeInfo"]["kubeletVersion"]

            # Simple version comparison, assuming semantic versioning.
            # This might need to be more robust for production use.
            upgrade_needed = kubelet_version < latest_version

            return ClusterUpgradeStatus(
                cluster_name=cluster["name"],
                current_version=kubelet_version,
                latest_version=latest_version,
                upgrade_needed=upgrade_needed,
            )
        except (json.JSONDecodeError, KeyError) as e:
            return ClusterUpgradeStatus(
                cluster_name=cluster["name"],
                current_version="N/A",
                latest_version=latest_version,
                upgrade_needed=False,
                error=f"Failed to parse node information: {e}",
            )

    async def _run_command(self, cmd: List[str]) -> Dict[str, Any]:
        """Run a shell command asynchronously."""
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        return {
            "returncode": process.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
        }

    def get_schema(self) -> Dict[str, Any]:
        """Define the JSON schema for function parameters."""
        return {
            "type": "object",
            "properties": {
                "kubeconfig": {
                    "type": "string",
                    "description": "Path to the kubeconfig file.",
                },
            },
            "required": [],
        }
