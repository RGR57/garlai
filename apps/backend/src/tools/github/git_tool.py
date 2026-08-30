import asyncio
import subprocess
from pathlib import Path
from typing import Any

from src.models.tool_result import ToolResult
from src.tools.base_tool import BaseTool


class GitTool(BaseTool):

    TIMEOUT_SECONDS = 20

    def __init__(
        self,
        workspace_root: str | None = None,
    ):
        self.workspace_root = Path(
            workspace_root or Path.cwd()
        ).resolve()

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return (
            "Provides read-only access to the local Git repository. "
            "Supported actions: status, branch, log, diff. "
            "Arguments: action and optional limit."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "status",
                        "branch",
                        "log",
                        "diff",
                    ],
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum commits returned by git log."
                    ),
                },
            },
            "required": [
                "action"
            ],
        }

    async def execute(
        self,
        **kwargs: Any,
    ) -> ToolResult:

        action = kwargs.get(
            "action"
        )

        limit = kwargs.get(
            "limit",
            10,
        )

        if action == "status":
            command = [
                "git",
                "status",
                "--short",
            ]

        elif action == "branch":
            command = [
                "git",
                "branch",
                "--show-current",
            ]

        elif action == "log":

            limit = max(
                1,
                min(limit, 50),
            )

            command = [
                "git",
                "log",
                f"-{limit}",
                "--oneline",
            ]

        elif action == "diff":
            command = [
                "git",
                "diff",
            ]

        else:

            return self._failure(
                f"Unsupported Git action: {action}"
            )

        try:

            result = await asyncio.to_thread(
                self._run,
                command,
            )

        except subprocess.TimeoutExpired:

            return self._failure(
                "Git command timed out."
            )

        except Exception as exc:

            return self._failure(
                f"{type(exc).__name__}: {str(exc)}"
            )

        stdout = (
            result.stdout or ""
        ).strip()

        stderr = (
            result.stderr or ""
        ).strip()

        if result.returncode != 0:

            return self._failure(
                stderr
                or stdout
                or (
                    "Git command failed with "
                    f"exit code {result.returncode}."
                )
            )

        # Empty git status/diff is valid.
        if not stdout:

            if action == "status":
                stdout = "Working tree clean."

            elif action == "diff":
                stdout = "No unstaged changes."

        return ToolResult(
            success=True,
            tool_name=self.name,
            output=stdout,
            metadata={
                "action": action,
                "return_code": result.returncode,
            },
        )

    def _run(
        self,
        command: list[str],
    ) -> subprocess.CompletedProcess:

        return subprocess.run(
            command,
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            timeout=self.TIMEOUT_SECONDS,
            shell=False,
        )

    def _failure(
        self,
        error: str,
    ) -> ToolResult:

        return ToolResult(
            success=False,
            tool_name=self.name,
            output=None,
            metadata={
                "error": error,
            },
        )