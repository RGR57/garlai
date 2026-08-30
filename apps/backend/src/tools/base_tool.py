from abc import ABC, abstractmethod
from typing import Any

from src.models.tool_result import ToolResult


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