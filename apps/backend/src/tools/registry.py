from src.tools.calculator_tool import CalculatorTool
from src.tools.filesystem.filesystem_tool import FilesystemTool
from src.tools.terminal.terminal_tool import TerminalTool
from src.tools.github.git_tool import GitTool
from src.tools.tool_manager import ToolManager
from src.services.browser_session_service import BrowserSessionService
from src.tools.browser.browser_navigate_tool import BrowserNavigateTool
from src.tools.browser.browser_observe_tool import BrowserObserveTool
from src.tools.browser.browser_select_tool import BrowserSelectTool
from src.tools.browser.browser_fill_tool import BrowserFillTool
from src.tools.browser.browser_submit_tool import BrowserSubmitTool


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

    @staticmethod
    def register_browser_tools(
        manager: ToolManager,
        browser_sessions: BrowserSessionService,
    ) -> None:
        manager.register(BrowserNavigateTool(browser_sessions))
        manager.register(BrowserObserveTool(browser_sessions))
        manager.register(BrowserSelectTool(browser_sessions))
        manager.register(BrowserFillTool(browser_sessions))
        manager.register(BrowserSubmitTool(browser_sessions))
