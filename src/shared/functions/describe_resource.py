"""Function to get detailed information about a specific Kubernetes resource."""

import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from src.shared.base_functions import BaseFunction


@dataclass
class DescribeResourceInput:
    """Input parameters for the describe_resource function."""

    context: str
    namespace: str
    resource_type: str
    resource_name: str
    kubeconfig: str = ""


@dataclass
class DescribeResourceOutput:
    """Standardised response from the describe_resource function."""

    status: str
    details: Dict[str, Any] = field(default_factory=dict)


class DescribeResourceFunction(BaseFunction):
    """
    Function to get detailed, human-readable information about a specific Kubernetes resource,
    similar to 'kubectl describe'.
    """

    def __init__(self):
        super().__init__(
            name="describe_resource",
            description="Get a detailed, human-readable description of a specific Kubernetes resource, including its state, configuration, and recent events. This is equivalent to running 'kubectl describe'.",
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute the describe_resource function.
        """
        try:
            params = DescribeResourceInput(**kwargs)

            # Build the kubectl describe command
            cmd = [
                "kubectl",
                "describe",
                params.resource_type,
                params.resource_name,
                "--context",
                params.context,
                "--namespace",
                params.namespace,
            ]

            if params.kubeconfig:
                cmd.extend(["--kubeconfig", params.kubeconfig])

            # Run the command
            result = await self._run_command(cmd)

            # Return the result
            if result["returncode"] == 0:
                response = {"status": "success", "description": result["stdout"]}
                return asdict(DescribeResourceOutput(status="success", details=response))
            else:
                err = {"status": "error", "error": result["stderr"] or result["stdout"]}
                return asdict(DescribeResourceOutput(status="error", details=err))

        except Exception as e:
            err = {"status": "error", "error": f"Failed to describe resource: {str(e)}"}
            return asdict(DescribeResourceOutput(status="error", details=err))

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
                    "description": "The namespace of the resource.",
                },
                "resource_type": {
                    "type": "string",
                    "description": "The type of the resource (e.g., deployment, pod, service).",
                },
                "resource_name": {
                    "type": "string",
                    "description": "The name of the resource.",
                },
                "kubeconfig": {
                    "type": "string",
                    "description": "Optional path to the kubeconfig file.",
                },
            },
            "required": ["context", "namespace", "resource_type", "resource_name"],
        }
