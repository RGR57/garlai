import unittest

from src.models.execution_state import ExecutionState
from src.models.tool_result import ToolResult
from src.services.approval_service import ApprovalService
from src.tools.base_tool import BaseTool
from src.tools.tool_manager import ToolManager


class FakeTool(BaseTool):

    def __init__(
        self,
        *,
        result: ToolResult | None = None,
        raises: Exception | None = None,
    ):
        self.result = result or ToolResult(
            success=True,
            tool_name="fake",
            output="done",
        )
        self.raises = raises
        self.calls = []

    @property
    def name(self) -> str:
        return "fake"

    @property
    def description(self) -> str:
        return "Fake approval test tool."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "value": {
                    "type": "string",
                },
            },
            "required": [
                "value",
            ],
        }

    async def execute(
        self,
        **kwargs,
    ) -> ToolResult:
        self.calls.append(kwargs)

        if self.raises:
            raise self.raises

        return self.result


class ApprovalServiceTests(
    unittest.IsolatedAsyncioTestCase
):

    def make_service(
        self,
        tool: FakeTool | None = None,
    ) -> tuple[ApprovalService, FakeTool]:
        manager = ToolManager()
        fake_tool = tool or FakeTool()
        manager.register(fake_tool)
        return ApprovalService(manager), fake_tool

    def make_pending_state(
        self,
    ) -> ExecutionState:
        state = ExecutionState()
        state.require_approval(
            step_id=2,
            tool_name="fake",
            arguments={
                "value": "approved input",
            },
            reason="test approval",
            risk_level="high",
        )
        return state

    async def test_approve_executes_exact_pending_action_and_audits_decision(
        self,
    ):
        service, fake_tool = self.make_service()
        state = self.make_pending_state()

        response = await service.approve(state)

        self.assertEqual(response, "done")
        self.assertEqual(
            fake_tool.calls,
            [
                {
                    "value": "approved input",
                }
            ],
        )
        self.assertFalse(state.approval_required)
        self.assertEqual(state.variables["step2"], "done")
        self.assertEqual(len(state.history), 1)
        self.assertTrue(state.history[0].success)
        self.assertEqual(state.history[0].tool, "fake")
        self.assertEqual(len(state.approval_history), 1)
        self.assertEqual(
            state.approval_history[0].decision,
            "approved",
        )
        self.assertEqual(
            state.approval_history[0].result,
            "done",
        )

    async def test_reject_audits_decision_before_clearing_pending_state(
        self,
    ):
        service, fake_tool = self.make_service()
        state = self.make_pending_state()

        response = await service.reject(state)

        self.assertEqual(
            response,
            "Pending action rejected. Nothing was executed.",
        )
        self.assertEqual(fake_tool.calls, [])
        self.assertFalse(state.approval_required)
        self.assertEqual(len(state.history), 0)
        self.assertEqual(len(state.approval_history), 1)
        self.assertEqual(
            state.approval_history[0].decision,
            "rejected",
        )

    async def test_incomplete_approval_state_fails_cleanly(
        self,
    ):
        service, fake_tool = self.make_service()
        state = ExecutionState(
            approval_required=True,
        )

        response = await service.approve(state)

        self.assertIn(
            "execution state was incomplete",
            response,
        )
        self.assertEqual(fake_tool.calls, [])
        self.assertFalse(state.approval_required)
        self.assertEqual(len(state.history), 0)

    async def test_approved_tool_failure_is_recorded_and_audited(
        self,
    ):
        failing_tool = FakeTool(
            result=ToolResult(
                success=False,
                tool_name="fake",
                output=None,
                metadata={
                    "error": "tool failed",
                },
            )
        )
        service, _ = self.make_service(failing_tool)
        state = self.make_pending_state()

        response = await service.approve(state)

        self.assertEqual(response, "tool failed")
        self.assertFalse(state.approval_required)
        self.assertEqual(len(state.history), 1)
        self.assertFalse(state.history[0].success)
        self.assertEqual(state.history[0].error, "tool failed")
        self.assertEqual(len(state.approval_history), 1)
        self.assertEqual(
            state.approval_history[0].decision,
            "approved",
        )
        self.assertEqual(
            state.approval_history[0].result,
            "tool failed",
        )


if __name__ == "__main__":
    unittest.main()
