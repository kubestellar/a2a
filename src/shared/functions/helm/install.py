"""Helm install function."""

import asyncio
import time
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional

from src.shared.base_functions import BaseFunction


@dataclass
class HelmInstallParams:
    """Dataclass for Helm install parameters."""

    chart_name: str
    release_name: str = ""
    chart_version: str = ""
    repository_url: str = ""
    namespace: str = "default"
    values_file: str = ""
    set_values: Optional[List[str]] = None
    create_namespace: bool = True
    wait: bool = False
    kubeconfig: str = ""
    target_cluster: str = ""


class HelmInstallFunction(BaseFunction):
    """A function to install a Helm chart."""

    def __init__(self) -> None:
        super().__init__(
            name="helm_install",
            description="Install a Helm chart on a specified cluster.",
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute the helm install command.
        """
        start_time = time.perf_counter()
        try:
            valid_kwargs = {
                field.name: kwargs[field.name]
                for field in fields(HelmInstallParams)
                if field.name in kwargs
            }
            params = HelmInstallParams(**valid_kwargs)

            cmd = ["helm", "install"]

            release_name = params.release_name or f"{params.chart_name}-release"
            cmd.append(release_name)

            cmd.append(params.chart_name)

            if params.repository_url:
                cmd.extend(["--repo", params.repository_url])
            if params.chart_version:
                cmd.extend(["--version", params.chart_version])
            if params.namespace:
                cmd.extend(["--namespace", params.namespace])
            if params.create_namespace:
                cmd.append("--create-namespace")
            if params.values_file:
                cmd.extend(["-f", params.values_file])
            if params.set_values:
                for val in params.set_values:
                    cmd.extend(["--set", val])
            if params.wait:
                cmd.append("--wait")
            if params.kubeconfig:
                cmd.extend(["--kubeconfig", params.kubeconfig])
            if params.target_cluster:
                cmd.extend(["--kube-context", params.target_cluster])

            cmd_start_time = time.perf_counter()
            result = await self._run_command(cmd)
            cmd_duration = time.perf_counter() - cmd_start_time

            total_duration = time.perf_counter() - start_time

            debug_info = {
                "command_executed": " ".join(cmd),
                "total_tool_duration_seconds": f"{total_duration:.4f}",
                "helm_command_duration_seconds": f"{cmd_duration:.4f}",
            }

            if result["returncode"] == 0:
                return {
                    "status": "success",
                    "output": result["stdout"],
                    "debug": debug_info,
                }
            else:
                return {
                    "status": "error",
                    "error": result["stderr"] or result["stdout"],
                    "debug": debug_info,
                }

        except Exception as e:
            total_duration = time.perf_counter() - start_time
            return {
                "status": "error",
                "error": str(e),
                "debug": {"total_tool_duration_seconds": f"{total_duration:.4f}"},
            }

    async def _run_command(self, cmd: List[str]) -> Dict[str, Any]:
        """Run a shell command asynchronously."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return {
                "returncode": process.returncode,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
            }
        except Exception as e:
            return {"returncode": 1, "stdout": "", "stderr": str(e)}

    def get_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for the function."""
        return {
            "type": "object",
            "properties": {
                "chart_name": {
                    "type": "string",
                    "description": "The name of the chart to install.",
                },
                "release_name": {
                    "type": "string",
                    "description": "The name of the release.",
                },
                "chart_version": {
                    "type": "string",
                    "description": "The version of the chart to install.",
                },
                "repository_url": {
                    "type": "string",
                    "description": "The URL of the chart repository.",
                },
                "namespace": {
                    "type": "string",
                    "description": "The namespace to install the chart in.",
                },
                "values_file": {
                    "type": "string",
                    "description": "Path to a values file.",
                },
                "set_values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Set values on the command line.",
                },
                "create_namespace": {
                    "type": "boolean",
                    "description": "Create the namespace if it does not exist.",
                },
                "wait": {
                    "type": "boolean",
                    "description": "Wait for the release to be deployed.",
                },
                "kubeconfig": {
                    "type": "string",
                    "description": "Path to the kubeconfig file.",
                },
                "target_cluster": {
                    "type": "string",
                    "description": "The name of the cluster context to install to.",
                },
            },
            "required": ["chart_name"],
        }
