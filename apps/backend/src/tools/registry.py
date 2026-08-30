from src.tools.calculator_tool import CalculatorTool
from src.tools.filesystem.filesystem_tool import FilesystemTool
from src.tools.terminal.terminal_tool import TerminalTool
from src.tools.github.git_tool import GitTool
from src.tools.tool_manager import ToolManager


class ToolRegistry:

    @staticmethod
    def register_all(
        manager: ToolManager,
    ) -> None:

        manager.register(
            CalculatorTool()
        )

        manager.register(
            TerminalTool()
        )

        manager.register(
            FilesystemTool()
        )

        manager.register(
            GitTool()
        )
