"""Utility functions for subprocess management and cancellation."""

import asyncio
from typing import Any, Dict, List, Optional


async def run_subprocess_with_cancellation(
    cmd: List[str], stdin_data: Optional[bytes] = None
) -> Dict[str, Any]:
    """
    Run a subprocess with proper cancellation support.

    When the task is cancelled (e.g., by Ctrl+C), the subprocess will be terminated.

    Args:
        cmd: Command to execute as a list of strings
        stdin_data: Optional data to send to stdin

    Returns:
        Dictionary with returncode, stdout, and stderr

    Raises:
        asyncio.CancelledError: If the task is cancelled
    """
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if stdin_data else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await process.communicate(input=stdin_data)
        return {
            "returncode": process.returncode,
            "stdout": stdout.decode() if stdout else "",
            "stderr": stderr.decode() if stderr else "",
        }
    except asyncio.CancelledError:
        # Task was cancelled, terminate the subprocess
        try:
            process.terminate()
            # Give it a moment to terminate gracefully
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                # If it doesn't terminate, kill it forcefully
                process.kill()
                await process.wait()
        except (ProcessLookupError, OSError):
            # Process might have already finished
            pass
        # Re-raise the cancellation so the caller knows it was cancelled
        raise


async def run_shell_command_with_cancellation(cmd: List[str]) -> Dict[str, Any]:
    """
    Run a shell command with proper cancellation support.
    This is a convenience wrapper for run_subprocess_with_cancellation.

    Args:
        cmd: Command to execute as a list of strings

    Returns:
        Dictionary with returncode, stdout, and stderr
    """
    return await run_subprocess_with_cancellation(cmd)
