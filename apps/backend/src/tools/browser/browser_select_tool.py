from src.models.browser import BrowserTarget
from src.models.tool_result import ToolInvocationOutcome, ToolResult
from src.services.browser_session_service import BrowserSessionService
from src.tools.base_tool import BaseTool, ToolInvocationContext


class BrowserSelectTool(BaseTool):
    def __init__(self, browser_sessions: BrowserSessionService) -> None:
        self.browser_sessions = browser_sessions

    @property
    def name(self) -> str:
        return "browser_select"

    @property
    def description(self) -> str:
        return "Select a verified semantic browser target as a preparatory action."

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {"target": {"type": "object"}}, "required": ["target"]}

    async def execute(self, **kwargs) -> ToolResult:
        raise RuntimeError("Browser selection requires a durable invocation context.")

    async def execute_with_context(self, arguments: dict, invocation: ToolInvocationContext) -> ToolResult:
        execution_id, operation_id = self._identities(invocation)
        receipt = await self.browser_sessions.select(
            execution_id,
            BrowserTarget.from_payload(arguments["target"]),
            operation_id,
        )
        return ToolResult(
            success=True,
            tool_name=self.name,
            output={"receipt": receipt},
            invocation_outcome=ToolInvocationOutcome.CONFIRMED,
        )

    @staticmethod
    def _identities(invocation: ToolInvocationContext) -> tuple[str, str]:
        if not invocation.execution_id or not invocation.operation_id:
            raise ValueError("Browser selection requires durable execution and operation identities.")
        return invocation.execution_id, invocation.operation_id
