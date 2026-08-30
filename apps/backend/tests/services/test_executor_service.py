import unittest

from src.models.execution_state import ExecutionState
from src.models.plan import ExecutionPlan, PlanStep
from src.models.tool_result import ToolResult
from src.services.context_builder import ContextBuilder
from src.services.decision_service import DecisionService
from src.services.executor_service import ExecutorService
from src.services.llm_service import LLMService
from src.services.permission_service import PermissionService
from src.services.variable_resolver import VariableResolver
from src.models.decision import DecisionType
from src.tools.base_tool import BaseTool
from src.tools.tool_manager import ToolManager


class RecordingTerminalTool(BaseTool):

    def __init__(self):
        self.calls = []

    @property
    def name(self) -> str:
        return "terminal"

    @property
    def description(self) -> str:
        return "Recording terminal tool."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                },
            },
            "required": [
                "query",
            ],
        }

    async def execute(
        self,
        **kwargs,
    ) -> ToolResult:
        self.calls.append(kwargs)
        return ToolResult(
            success=True,
            tool_name=self.name,
            output="executed",
        )


class ExecutorServiceTests(
    unittest.IsolatedAsyncioTestCase
):

    def make_executor(
        self,
        tool: BaseTool,
    ) -> ExecutorService:
        manager = ToolManager()
        manager.register(tool)
        return ExecutorService(
            llm=LLMService(),
            context_builder=ContextBuilder(),
            tool_manager=manager,
            variable_resolver=VariableResolver(),
            permission_service=PermissionService(),
        )

    async def test_denied_tool_action_is_not_executed(
        self,
    ):
        tool = RecordingTerminalTool()
        executor = self.make_executor(tool)
        state = ExecutionState()
        plan = ExecutionPlan(
            steps=[
                PlanStep(
                    id=1,
                    action="run destructive command",
                    tool="terminal",
                    input="rm -rf /",
                    arguments={
                        "query": "rm -rf /",
                    },
                )
            ]
        )

        result = await executor.execute(
            messages=[],
            plan=plan,
            state=state,
        )

        self.assertEqual(tool.calls, [])
        self.assertIn(
            "blocked",
            result.lower(),
        )
        self.assertEqual(len(state.history), 1)
        self.assertFalse(state.history[0].success)
        self.assertEqual(state.history[0].tool, "terminal")

    async def test_approval_required_action_is_not_executed_until_approved(
        self,
    ):
        tool = RecordingTerminalTool()
        executor = self.make_executor(tool)
        state = ExecutionState()
        plan = ExecutionPlan(
            steps=[
                PlanStep(
                    id=1,
                    action="install package",
                    tool="terminal",
                    input="pip install example-package",
                    arguments={
                        "query": "pip install example-package",
                    },
                )
            ]
        )

        result = await executor.execute(
            messages=[],
            plan=plan,
            state=state,
        )

        decision = await DecisionService().decide(
            state
        )

        self.assertEqual(tool.calls, [])
        self.assertIn(
            "Approval required",
            result,
        )
        self.assertEqual(
            decision.action,
            DecisionType.WAIT_FOR_APPROVAL,
        )
        self.assertTrue(state.approval_required)
        self.assertEqual(state.pending_tool, "terminal")
        self.assertEqual(
            state.pending_arguments,
            {
                "query": "pip install example-package",
            },
        )
        self.assertEqual(len(state.history), 1)
        self.assertFalse(state.history[0].success)

    async def test_allowed_tool_action_executes_once_and_records_state(
        self,
    ):
        tool = RecordingTerminalTool()
        executor = self.make_executor(tool)
        state = ExecutionState()
        plan = ExecutionPlan(
            steps=[
                PlanStep(
                    id=1,
                    action="inspect environment",
                    tool="terminal",
                    input="echo hello",
                    arguments={
                        "query": "echo hello",
                    },
                )
            ]
        )

        result = await executor.execute(
            messages=[],
            plan=plan,
            state=state,
        )

        self.assertEqual(
            tool.calls,
            [
                {
                    "query": "echo hello",
                }
            ],
        )
        self.assertEqual(result, "executed")
        self.assertEqual(len(state.history), 1)
        self.assertTrue(state.history[0].success)
        self.assertEqual(
            state.variables["step1"],
            "executed",
        )


if __name__ == "__main__":
    unittest.main()
