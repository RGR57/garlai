import json

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

    def get_tool_definitions(self) -> list[dict]:
        """
        Return machine-readable definitions for
        every registered GARL tool.
        """

        definitions = []

        for tool in self.tool_manager.list_tools():

            definitions.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
            )

        return definitions

    def get_tool_descriptions(self) -> str:
        """
        Return planner-friendly tool definitions.
        """

        definitions = self.get_tool_definitions()

        if not definitions:
            return "No tools are currently available."

        return json.dumps(
            definitions,
            indent=2,
        )