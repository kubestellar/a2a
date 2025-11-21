"""Helm repository management functions."""

import asyncio
from typing import Any, Dict, List

from src.shared.base_functions import BaseFunction


class HelmRepoFunction(BaseFunction):
    """A collection of Helm repository management functions."""

    def __init__(self) -> None:
        super().__init__(
            name="helm_repo",
            description="Manage Helm repositories. Supports 'add', 'update', and 'list' operations.",
        )

    async def execute(
        self, operation: str, repo_name: str = "", repo_url: str = ""
    ) -> Dict[str, Any]:
        """
        Execute a Helm repository operation.

        Args:
            operation: The operation to perform ('add', 'update', 'list').
            repo_name: The name of the repository (for 'add').
            repo_url: The URL of the repository (for 'add').

        Returns:
            A dictionary with the result of the operation.
        """
        if operation == "add":
            if not repo_name or not repo_url:
                return {
                    "status": "error",
                    "error": "repo_name and repo_url are required for 'add' operation.",
                }
            cmd = ["helm", "repo", "add", repo_name, repo_url]
        elif operation == "update":
            cmd = ["helm", "repo", "update"]
        elif operation == "list":
            cmd = ["helm", "repo", "list"]
        else:
            return {"status": "error", "error": f"Unsupported operation: {operation}"}

        result = await self._run_command(cmd)

        if result["returncode"] == 0:
            return {"status": "success", "output": result["stdout"]}
        else:
            return {
                "status": "error",
                "error": result["stderr"] or result["stdout"],
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
                "operation": {
                    "type": "string",
                    "description": "The repository operation to perform.",
                    "enum": ["add", "update", "list"],
                },
                "repo_name": {
                    "type": "string",
                    "description": "The name for the repository (required for 'add').",
                },
                "repo_url": {
                    "type": "string",
                    "description": "The URL for the repository (required for 'add').",
                },
            },
            "required": ["operation"],
        }
