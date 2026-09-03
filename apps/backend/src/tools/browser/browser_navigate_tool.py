from src.models.tool_result import ToolInvocationOutcome, ToolResult
from src.services.browser_session_service import BrowserSessionService
from src.tools.base_tool import BaseTool, ToolInvocationContext


class BrowserNavigateTool(BaseTool):
    def __init__(self, browser_sessions: BrowserSessionService) -> None:
        self.browser_sessions = browser_sessions

    @property
    def name(self) -> str:
        return "browser_navigate"

    @property
    def description(self) -> str:
        return "Navigate the execution-scoped browser session to an allowed URL."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Allowed public HTTPS URL to navigate to.",
                }
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        raise RuntimeError("Browser navigation requires a durable invocation context.")

    async def execute_with_context(
        self,
        arguments: dict,
        invocation: ToolInvocationContext,
    ) -> ToolResult:
        execution_id = self._execution_id(invocation)
        final_url = await self.browser_sessions.navigate(execution_id, arguments["url"])
        return ToolResult(
            success=True,
            tool_name=self.name,
            output={
                "browser_session_execution_id": execution_id,
                "url": final_url,
            },
            invocation_outcome=ToolInvocationOutcome.CONFIRMED,
        )

    @staticmethod
    def _execution_id(invocation: ToolInvocationContext) -> str:
        if not invocation.execution_id:
            raise ValueError("Browser navigation requires a durable execution identity.")
        return invocation.execution_id
