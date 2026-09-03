from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.models.tool_result import ToolResult


@dataclass(frozen=True)
class ToolInvocationContext:
    """Execution-owned context that is never supplied by planner arguments."""

    execution_id: str | None
    step_id: int | None
    operation_id: str | None
    approved_payload_hash: str | None = None


@dataclass(frozen=True)
class ToolPreflight:
    """A provider may decline a consequential dispatch before it is claimed."""

    ready: bool
    reason: str | None = None


class BaseTool(ABC):
    """
    Base interface for every GARL tool.

    Every tool must describe:
    - its name
    - its purpose
    - the input it accepts
    - how it executes
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    def supports_idempotency_key(self) -> bool:
        """Whether this tool can safely reuse a stable GARL operation ID."""
        return False

    @property
    def input_schema(self) -> dict[str, Any]:
        """
        Describes the arguments accepted by the tool.

        Tools may override this when they require
        structured or specialized inputs.
        """
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Input query for the tool.",
                }
            },
            "required": ["query"],
        }

    @abstractmethod
    async def execute(
        self,
        **kwargs,
    ) -> ToolResult:
        ...

    async def execute_with_context(
        self,
        arguments: dict[str, Any],
        invocation: ToolInvocationContext,
    ) -> ToolResult:
        """Backward-compatible context-aware execution hook."""
        return await self.execute(**arguments)

    async def preflight(
        self,
        arguments: dict[str, Any],
        invocation: ToolInvocationContext,
    ) -> ToolPreflight:
        """Legacy tools have no pre-dispatch reconciliation work."""
        return ToolPreflight(ready=True)
