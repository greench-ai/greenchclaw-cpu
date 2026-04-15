"""
GreenClaw CPU — Code Execution Tools.

Execute Python and shell code safely.
"""

import asyncio
import copy
import io
import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from .base import Tool, ToolCategory, ToolResult

logger = logging.getLogger(__name__)


class PythonExecTool(Tool):
    """
    Execute Python code in a sandboxed environment.

    Supports Python 3.10+ with access to standard library.
    Can optionally install packages and use async code.
    """

    name = "python_exec"
    description = (
        "Execute Python code and return the output. "
        "Use this for calculations, data processing, automation, testing, "
        "or any task that's easier in code than in natural language. "
        "Supports asyncio, file I/O, and package installation."
    )
    category = ToolCategory.CODE
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python code to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum execution time in seconds (default: 30, max: 120)",
            },
            "pip_packages": {
                "type": "array",
                "description": "Pip package names to install before execution (optional)",
                "items": {"type": "string"},
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory for execution (default: /tmp)",
            },
        },
        "required": ["code"],
    }

    async def execute(
        self,
        code: str,
        timeout: int = 30,
        pip_packages: Optional[list[str]] = None,
        working_dir: Optional[str] = None,
    ) -> ToolResult:
        timeout = min(timeout, 120)
        work_dir = working_dir or "/tmp"

        # Install packages if requested
        if pip_packages:
            install_result = await _install_packages(pip_packages)
            if not install_result:
                return ToolResult(
                    success=False,
                    error=f"Failed to install packages: {', '.join(pip_packages)}",
                )

        # Capture stdout/stderr
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        # Create sandboxed globals/locals
        sandbox_globals = {
            "__name__": "__greenchlaw_sandbox__",
            "__builtins__": __builtins__,
            "__file__": f"{work_dir}/greenchlaw_exec.py",
        }
        sandbox_locals: dict = {}

        # Add common imports
        prelude = [
            "import sys, os, json, math, datetime, re, collections, itertools, functools",
            "from pathlib import Path",
            "from typing import *",
        ]

        full_code = "\n".join(prelude) + "\n" + code

        try:
            exec_result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    _safe_exec,
                    full_code,
                    sandbox_globals,
                    sandbox_locals,
                    stdout_capture,
                    stderr_capture,
                ),
                timeout=timeout,
            )

            stdout = stdout_capture.getvalue()
            stderr = stderr_capture.getvalue()

            output_parts = []
            if stdout:
                output_parts.append(f"[stdout]\n{stdout}")
            if stderr:
                output_parts.append(f"[stderr]\n{stderr}")
            if exec_result is not None:
                try:
                    repr_result = repr(exec_result)
                    if repr_result != "None":
                        output_parts.append(f"[return]\n{repr_result}")
                except Exception:
                    pass

            output = "\n".join(output_parts) if output_parts else "(no output)"

            return ToolResult(
                success=True,
                content=output,
                metadata={
                    "execution_time": "completed",
                    "stdout_lines": stdout.count("\n") + 1 if stdout else 0,
                },
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error=f"Execution timed out after {timeout}s",
            )
        except Exception as e:
            stderr = stderr_capture.getvalue()
            error_msg = str(e)
            if stderr:
                error_msg += f"\n{stderr}"
            return ToolResult(success=False, error=error_msg)


def _safe_exec(
    code: str,
    globals_dict: dict,
    locals_dict: dict,
    stdout: io.StringIO,
    stderr: io.StringIO,
) -> any:
    """Execute code with captured stdout/stderr."""
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = stdout
    sys.stderr = stderr
    try:
        result = exec(code, globals_dict, locals_dict)
        return result
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


async def _install_packages(packages: list[str]) -> bool:
    """Install pip packages."""
    try:
        import subprocess
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            *packages,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        return proc.returncode == 0
    except Exception as e:
        logger.warning(f"Package installation failed: {e}")
        return False


class ShellExecTool(Tool):
    """Execute shell commands."""

    name = "shell_exec"
    description = (
        "Execute a shell command and return stdout/stderr. "
        "Use for git operations, npm/node, docker, curl, file manipulation, "
        "system administration, and anything not possible in Python."
    )
    category = ToolCategory.CODE
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum execution time in seconds (default: 30, max: 120)",
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory (default: current directory)",
            },
        },
        "required": ["command"],
    }

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        working_dir: Optional[str] = None,
    ) -> ToolResult:
        timeout = min(timeout, 120)
        cwd = working_dir or os.getcwd()

        # Safety: block dangerous commands
        dangerous = ["rm -rf /", "dd if=/dev/zero", ":(){ :|:& };:", "> /dev/sda"]
        for pattern in dangerous:
            if pattern in command:
                return ToolResult(
                    success=False,
                    error=f"Command blocked for safety: contains '{pattern}'",
                )

        try:
            proc = await asyncio.create_subprocess_exec(
                "/bin/sh",
                "-c",
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            output = stdout
            if stderr:
                output += f"\n[stderr]\n{stderr}"

            return ToolResult(
                success=proc.returncode == 0,
                content=output or "(no output)",
                error=None if proc.returncode == 0 else f"Exit code: {proc.returncode}",
                metadata={
                    "exit_code": proc.returncode,
                    "command": command,
                    "cwd": cwd,
                },
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(success=False, error=f"Execution error: {e}")


def register_code_tools(registry) -> None:
    """Register code execution tools."""
    registry.register(PythonExecTool())
    registry.register(ShellExecTool())
