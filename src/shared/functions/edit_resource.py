"""Directly edit a live Kubernetes resource on a specific cluster by providing a YAML patch."""

import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from src.shared.base_functions import BaseFunction


@dataclass
class EditResourceInput:
    """All parameters accepted by `edit_resource` bundled in a single object."""

    context: str
    namespace: str
    resource_type: str
    resource_name: str
    patch_yaml: str
    kubeconfig: str = ""


@dataclass
class EditResourceOutput:
    """Standardised response from `edit_resource`."""

    status: str
    details: Dict[str, Any] = field(default_factory=dict)


class EditResourceFunction(BaseFunction):
    """
    Function to directly edit a live Kubernetes resource by applying a YAML patch.
    This mimics the behavior of 'kubectl patch'.
    """

    def __init__(self):
        super().__init__(
            name="edit_resource",
            description="Directly edit a live Kubernetes resource on a specific cluster by providing a YAML patch. Ideal for making quick, targeted changes (e.g., updating replicas, changing an image tag) without needing the original source file.",
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute the resource edit using a single `EditResourceInput` bundle.
        The agent should supply parameters that conform to that dataclass.
        """
        try:
            params = EditResourceInput(**kwargs)

            # Build the kubectl patch command
            cmd = [
                "kubectl",
                "patch",
                params.resource_type,
                params.resource_name,
                "--context",
                params.context,
                "--namespace",
                params.namespace,
                "--type",
                "merge",  # Merge patch is intuitive for YAML
                "--patch",
                params.patch_yaml,
            ]

            if params.kubeconfig:
                cmd.extend(["--kubeconfig", params.kubeconfig])

            # Run the command
            result = await self._run_command(cmd)

            # Return the result
            if result["returncode"] == 0:
                response = {"status": "success", "output": result["stdout"]}
                return asdict(EditResourceOutput(status="success", details=response))
            else:
                err = {"status": "error", "error": result["stderr"] or result["stdout"]}
                return asdict(EditResourceOutput(status="error", details=err))

        except Exception as e:
            err = {"status": "error", "error": f"Failed to edit resource: {str(e)}"}
            return asdict(EditResourceOutput(status="error", details=err))

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
        """Define the JSON schema for function parameters."""
        return {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "The Kubernetes context (cluster name) to target.",
                },
                "namespace": {
                    "type": "string",
                    "description": "The namespace of the resource to edit.",
                },
                "resource_type": {
                    "type": "string",
                    "description": "The type of the resource (e.g., deployment, service, configmap).",
                },
                "resource_name": {
                    "type": "string",
                    "description": "The name of the resource to edit.",
                },
                "patch_yaml": {
                    "type": "string",
                    "description": "A YAML string containing the fields to add or modify. For example, to change replicas, use 'spec:\n  replicas: 3'. The agent is responsible for constructing this patch.",
                },
                "kubeconfig": {
                    "type": "string",
                    "description": "Optional path to the kubeconfig file.",
                },
            },
            "required": [
                "context",
                "namespace",
                "resource_type",
                "resource_name",
                "patch_yaml",
            ],
        }
