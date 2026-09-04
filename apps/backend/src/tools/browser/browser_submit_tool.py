from src.models.browser import BrowserTarget
from src.models.tool_result import ToolInvocationOutcome, ToolResult
from src.services.browser_session_service import BrowserSessionService
from src.tools.base_tool import BaseTool, ToolInvocationContext, ToolPreflight


class BrowserSubmitTool(BaseTool):
    def __init__(self, browser_sessions: BrowserSessionService) -> None:
        self.browser_sessions = browser_sessions

    @property
    def name(self) -> str:
        return "browser_submit"

    @property
    def description(self) -> str:
        return "Submit one approved, preflight-verified semantic browser commitment."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "object"},
                "expected_success_text": {"type": "string"},
            },
            "required": ["target"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        raise RuntimeError("Browser submit requires a durable approved invocation context.")

    async def preflight(self, arguments: dict, invocation: ToolInvocationContext) -> ToolPreflight:
        execution_id, operation_id = self._identities(invocation)
        ready, reason = await self.browser_sessions.preflight_submit(
            execution_id, BrowserTarget.from_payload(arguments["target"]), operation_id
        )
        return ToolPreflight(ready=ready, reason=reason)

    async def execute_with_context(self, arguments: dict, invocation: ToolInvocationContext) -> ToolResult:
        execution_id, operation_id = self._identities(invocation)
        receipt = await self.browser_sessions.submit(
            execution_id, BrowserTarget.from_payload(arguments["target"]), operation_id
        )
        return ToolResult(success=True, tool_name=self.name, output={"receipt": receipt}, invocation_outcome=ToolInvocationOutcome.CONFIRMED)

    @staticmethod
    def _identities(invocation: ToolInvocationContext) -> tuple[str, str]:
        if not invocation.execution_id or not invocation.operation_id or not invocation.approved_payload_hash:
            raise ValueError("Browser submit requires execution, operation, and approved payload identities.")
        return invocation.execution_id, invocation.operation_id
