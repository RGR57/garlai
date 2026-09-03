from src.models.tool_result import ToolInvocationOutcome, ToolResult
from src.services.browser_session_service import BrowserSessionService
from src.tools.base_tool import BaseTool, ToolInvocationContext


class BrowserObserveTool(BaseTool):
    def __init__(self, browser_sessions: BrowserSessionService) -> None:
        self.browser_sessions = browser_sessions

    @property
    def name(self) -> str:
        return "browser_observe"

    @property
    def description(self) -> str:
        return "Observe bounded structured page state in the execution-scoped browser session."

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs) -> ToolResult:
        raise RuntimeError("Browser observation requires a durable invocation context.")

    async def execute_with_context(
        self,
        arguments: dict,
        invocation: ToolInvocationContext,
    ) -> ToolResult:
        if not invocation.execution_id:
            raise ValueError("Browser observation requires a durable execution identity.")
        observation = await self.browser_sessions.observe(invocation.execution_id)
        return ToolResult(
            success=True,
            tool_name=self.name,
            output={
                "trust": "untrusted_external_page_data",
                "observation": observation.to_payload(),
            },
            invocation_outcome=ToolInvocationOutcome.CONFIRMED,
        )
