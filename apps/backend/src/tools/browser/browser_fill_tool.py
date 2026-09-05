from src.models.browser import BrowserTarget
from src.models.tool_result import ToolInvocationOutcome, ToolResult
from src.services.browser_session_service import BrowserSessionService
from src.tools.base_tool import BaseTool, ToolInvocationContext


class BrowserFillTool(BaseTool):
    def __init__(self, browser_sessions: BrowserSessionService) -> None:
        self.browser_sessions = browser_sessions

    @property
    def name(self) -> str:
        return "browser_fill"

    @property
    def description(self) -> str:
        return "Fill a verified non-sensitive semantic browser field."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"target": {"type": "object"}, "value": {"type": "string"}},
            "required": ["target", "value"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        raise RuntimeError("Browser fill requires a durable invocation context.")

    async def execute_with_context(self, arguments: dict, invocation: ToolInvocationContext) -> ToolResult:
        execution_id, operation_id = self._identities(invocation)
        target = BrowserTarget.from_payload(arguments["target"])
        if target.is_sensitive:
            raise ValueError("Browser fill refuses a sensitive field.")
        receipt = await self.browser_sessions.fill(
            execution_id,
            target,
            arguments["value"],
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
            raise ValueError("Browser fill requires durable execution and operation identities.")
        return invocation.execution_id, invocation.operation_id
