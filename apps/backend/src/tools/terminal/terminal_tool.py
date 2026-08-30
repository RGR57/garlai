import asyncio
import os
import subprocess

from src.models.tool_result import ToolResult
from src.tools.base_tool import BaseTool


class TerminalTool(BaseTool):

    TIMEOUT_SECONDS = 15

    @property
    def name(self) -> str:
        return "terminal"

    @property
    def description(self) -> str:
        return (
            "Executes approved read-only terminal commands for "
            "inspecting the local development environment. "
            "Useful for checking Python and pip versions, "
            "listing files, checking the current directory, "
            "and inspecting Git."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "An approved terminal command to execute."
                    ),
                }
            },
            "required": ["query"],
        }

    async def execute(
        self,
        **kwargs,
    ) -> ToolResult:

        command = kwargs.get("query")

        # ==========================================
        # VALIDATION
        # ==========================================

        if not command:
            return ToolResult(
                success=False,
                tool_name=self.name,
                output=None,
                metadata={
                    "error": "No terminal command provided."
                },
            )

        command = command.strip()

        if not self._is_allowed(command):
            return ToolResult(
                success=False,
                tool_name=self.name,
                output=None,
                metadata={
                    "command": command,
                    "error": (
                        f"Terminal command is not allowed: "
                        f"{command}"
                    ),
                },
            )

        # ==========================================
        # EXECUTION
        # ==========================================

        try:

            result = await asyncio.to_thread(
                self._run_command,
                command,
            )

            stdout_text = (
                result.stdout or ""
            ).strip()

            stderr_text = (
                result.stderr or ""
            ).strip()

            # ======================================
            # COMMAND FAILED
            # ======================================

            if result.returncode != 0:

                error_message = (
                    stderr_text
                    or stdout_text
                    or (
                        "Command failed with exit code "
                        f"{result.returncode}."
                    )
                )

                return ToolResult(
                    success=False,
                    tool_name=self.name,
                    output=stdout_text or None,
                    metadata={
                        "command": command,
                        "return_code": result.returncode,
                        "stdout": stdout_text,
                        "stderr": stderr_text,
                        "error": error_message,
                    },
                )

            # ======================================
            # SUCCESS
            # ======================================

            output = (
                stdout_text
                or stderr_text
            )

            return ToolResult(
                success=True,
                tool_name=self.name,
                output=output,
                metadata={
                    "command": command,
                    "return_code": result.returncode,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                },
            )

        # ==========================================
        # TIMEOUT
        # ==========================================

        except subprocess.TimeoutExpired:

            return ToolResult(
                success=False,
                tool_name=self.name,
                output=None,
                metadata={
                    "command": command,
                    "error": (
                        "Terminal command exceeded "
                        f"the {self.TIMEOUT_SECONDS} "
                        "second timeout."
                    ),
                },
            )

        # ==========================================
        # UNEXPECTED FAILURE
        # ==========================================

        except Exception as exc:

            return ToolResult(
                success=False,
                tool_name=self.name,
                output=None,
                metadata={
                    "command": command,
                    "error": (
                        f"{type(exc).__name__}: "
                        f"{str(exc)}"
                    ),
                },
            )

    def _run_command(
        self,
        command: str,
    ) -> subprocess.CompletedProcess:

        return subprocess.run(
            [
                "cmd.exe",
                "/d",
                "/s",
                "/c",
                command,
            ],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=self.TIMEOUT_SECONDS,
            shell=False,
        )

    def _is_allowed(
        self,
        command: str,
    ) -> bool:

        normalized = command.strip().lower()

        exact_commands = {
            "python --version",
            "python -v",
            "pip --version",
            "git status",
            "git branch",
            "git log",
            "dir",
            "cd",
        }

        allowed_prefixes = (
            "echo ",
            "where ",
        )

        if normalized in exact_commands:
            return True

        return normalized.startswith(
            allowed_prefixes
        )