"""Helm list function."""

import asyncio
from dataclasses import dataclass, fields
from typing import Any, Dict, List

from src.shared.base_functions import BaseFunction


@dataclass
class HelmListParams:
    """Dataclass for Helm list parameters."""

    namespace: str = ""
    all_namespaces: bool = False
    kubeconfig: str = ""
    target_cluster: str = ""


class HelmListFunction(BaseFunction):
    """A function to list Helm releases."""

    def __init__(self) -> None:
        super().__init__(
            name="helm_list",
            description="List Helm releases on a specified cluster.",
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute the helm list command.
        """
        try:
            valid_kwargs = {
                field.name: kwargs[field.name]
                for field in fields(HelmListParams)
                if field.name in kwargs
            }
            params = HelmListParams(**valid_kwargs)

            cmd = ["helm", "list"]

            if params.namespace:
                cmd.extend(["--namespace", params.namespace])
            if params.all_namespaces:
                cmd.append("--all-namespaces")
            if params.kubeconfig:
                cmd.extend(["--kubeconfig", params.kubeconfig])
            if params.target_cluster:
                cmd.extend(["--kube-context", params.target_cluster])

            result = await self._run_command(cmd)

            if result["returncode"] == 0:
                return {"status": "success", "output": result["stdout"]}
            else:
                return {
                    "status": "error",
                    "error": result["stderr"] or result["stdout"],
                }

        except Exception as e:
            return {"status": "error", "error": str(e)}

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
                "namespace": {"type": "string", "description": "The namespace to list releases in."},
                "all_namespaces": {"type": "boolean", "description": "List releases in all namespaces."},
                "kubeconfig": {"type": "string", "description": "Path to the kubeconfig file."},
                "target_cluster": {"type": "string", "description": "The name of the cluster context."},
            },
        }
