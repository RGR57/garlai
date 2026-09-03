import json
from collections.abc import Iterable

from src.tools.tool_manager import ToolManager


class ToolCatalog:

    def __init__(
        self,
        tool_manager: ToolManager,
    ):
        self.tool_manager = tool_manager

    def get_tool_names(self) -> list[str]:
        return [
            tool.name
            for tool in self.tool_manager.list_tools()
        ]

    def get_tool_definitions(
        self,
        eligible_tool_names: Iterable[str] | None = None,
    ) -> list[dict]:
        """
        Return machine-readable definitions for
        every registered GARL tool.
        """

        eligible_names = (
            set(eligible_tool_names)
            if eligible_tool_names is not None
            else None
        )
        definitions = []

        for tool in self.tool_manager.list_tools():

            if (
                eligible_names is not None
                and tool.name not in eligible_names
            ):
                continue

            definitions.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
            )

        return definitions

    def get_tool_descriptions(
        self,
        eligible_tool_names: Iterable[str] | None = None,
    ) -> str:
        """
        Return planner-friendly tool definitions.
        """

        definitions = self.get_tool_definitions(eligible_tool_names)

        if not definitions:
            return "No tools are currently available."

        return json.dumps(
            definitions,
            indent=2,
        )
