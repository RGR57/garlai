from src.tools.tool_manager import ToolManager


class ToolRegistry:

    def __init__(
        self,
        tool_manager: ToolManager,
    ):
        self.tool_manager = tool_manager

    def get_tool_names(self) -> list[str]:
        """
        Return the names of all currently registered tools.
        """
        return [
            tool.name
            for tool in self.tool_manager.list_tools()
        ]

    def get_tool_descriptions(self) -> str:
        """
        Build a planner-friendly description of
        all currently registered tools.
        """

        tools = self.tool_manager.list_tools()

        if not tools:
            return "No tools are currently available."

        lines = []

        for tool in tools:

            description = getattr(
                tool,
                "description",
                "No description available.",
            )

            lines.append(
                f"- {tool.name}: {description}"
            )

        return "\n".join(lines)