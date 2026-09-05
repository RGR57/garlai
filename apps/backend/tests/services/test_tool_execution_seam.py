import tempfile
from pathlib import Path

import pytest

from src.models.durable_execution import DurableStep, ExecutionRun, canonical_payload_hash
from src.models.execution_state import ExecutionState
from src.models.plan import ExecutionPlan, PlanStep
from src.models.tool_result import ToolResult
from src.repositories.sqlite_durable_execution_repository import SQLiteDurableExecutionRepository
from src.services.approval_service import ApprovalService
from src.services.context_builder import ContextBuilder
from src.services.executor_service import ExecutorService
from src.services.permission_service import PermissionService
from src.services.variable_resolver import VariableResolver
from src.tools.base_tool import BaseTool, ToolInvocationContext, ToolPreflight
from src.tools.tool_manager import ToolManager


class ContextOnlyCalculatorTool(BaseTool):
    def __init__(self) -> None:
        self.contexts: list[ToolInvocationContext] = []

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "Context-only calculator for canonical seam tests."

    async def execute(self, **kwargs) -> ToolResult:
        raise AssertionError("Active orchestration bypassed ToolManager.execute.")

    async def execute_with_context(
        self, arguments: dict, invocation: ToolInvocationContext
    ) -> ToolResult:
        self.contexts.append(invocation)
        return ToolResult(success=True, tool_name=self.name, output="4")


class RecordingToolManager(ToolManager):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict, ToolInvocationContext]] = []

    async def execute(
        self, name: str, arguments: dict, invocation: ToolInvocationContext
    ) -> ToolResult:
        self.calls.append((name, arguments, invocation))
        return await super().execute(name, arguments, invocation)


class StaleSubmitTool(BaseTool):
    def __init__(self) -> None:
        self.dispatches = 0

    @property
    def name(self) -> str:
        return "browser_submit"

    @property
    def description(self) -> str:
        return "Refuses stale approved submit before dispatch."

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {"target": {"type": "object"}}, "required": ["target"]}

    async def execute(self, **kwargs) -> ToolResult:
        self.dispatches += 1
        return ToolResult(success=True, tool_name=self.name, output="dispatched")

    async def preflight(self, arguments: dict, invocation: ToolInvocationContext) -> ToolPreflight:
        return ToolPreflight(ready=False, reason="approved target no longer matches the page")


def executor(manager: ToolManager, repository=None) -> ExecutorService:
    return ExecutorService(
        llm=None,
        context_builder=ContextBuilder(),
        tool_manager=manager,
        variable_resolver=VariableResolver(),
        permission_service=PermissionService(),
        durable_repository=repository,
    )


@pytest.mark.anyio
async def test_durable_executor_uses_manager_and_propagates_execution_operation_context():
    with tempfile.TemporaryDirectory() as directory:
        repository = SQLiteDurableExecutionRepository(Path(directory) / "run.sqlite3")
        await repository.initialize()
        await repository.create_planning_run(ExecutionRun(execution_id="run-42", objective="calculate"))
        await repository.persist_validated_plan(
            "run-42",
            [
                DurableStep(
                    step_id=1,
                    ordinal=0,
                    action="calculate",
                    tool="calculator",
                    arguments={"query": "2 + 2"},
                    operation_id="op-calculate",
                    payload_hash="payload",
                )
            ],
        )
        manager = RecordingToolManager()
        tool = ContextOnlyCalculatorTool()
        manager.register(tool)

        result = await executor(manager, repository).execute_ready_step(
            "run-42", 1, [], ExecutionState()
        )

        assert result.success is True
        assert manager.calls[0][0] == "calculator"
        assert tool.contexts == [
            ToolInvocationContext("run-42", 1, "op-calculate")
        ]


@pytest.mark.anyio
async def test_non_durable_approval_executes_through_manager_seam():
    manager = RecordingToolManager()
    tool = ContextOnlyCalculatorTool()
    manager.register(tool)
    state = ExecutionState()
    state.require_approval(
        step_id=7,
        tool_name="calculator",
        arguments={"query": "2 + 2"},
        reason="test approval",
        risk_level="medium",
    )

    result = await ApprovalService(manager).approve(state)

    assert result == "4"
    assert manager.calls[0][0] == "calculator"
    assert tool.contexts == [ToolInvocationContext(None, 7, None)]


@pytest.mark.anyio
async def test_normal_executor_uses_manager_seam_for_an_ordinary_calculation():
    manager = RecordingToolManager()
    tool = ContextOnlyCalculatorTool()
    manager.register(tool)

    result = await executor(manager).execute(
        [],
        ExecutionPlan(
            steps=[PlanStep(id=1, action="calculate", tool="calculator", arguments={"query": "2 + 2"})]
        ),
        ExecutionState(),
    )

    assert result == "4"
    assert tool.contexts == [ToolInvocationContext(None, 1, None)]


@pytest.mark.anyio
async def test_approved_submit_preflight_blocks_dispatch_before_operation_claim():
    with tempfile.TemporaryDirectory() as directory:
        arguments = {"target": {"frozen": "target"}}
        payload_hash = canonical_payload_hash("browser_submit", "confirm", arguments)
        repository = SQLiteDurableExecutionRepository(Path(directory) / "submit.sqlite3")
        await repository.initialize()
        await repository.create_planning_run(ExecutionRun(execution_id="run-submit", objective="submit"))
        await repository.persist_validated_plan(
            "run-submit",
            [DurableStep(step_id=1, ordinal=0, action="confirm", tool="browser_submit", arguments=arguments, operation_id="op-submit", payload_hash=payload_hash)],
        )
        manager = RecordingToolManager()
        submit = StaleSubmitTool()
        manager.register(submit)

        result = await executor(manager, repository).execute_ready_step(
            "run-submit", 1, [], ExecutionState(), approved_payload_hash=payload_hash
        )

        assert result.success is False
        assert "preflight" in result.error.lower()
        assert submit.dispatches == 0
        assert await repository.operation_events("op-submit") == []
