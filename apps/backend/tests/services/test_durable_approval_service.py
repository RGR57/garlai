import tempfile
import unittest
from pathlib import Path

from src.models.durable_execution import (
    ApprovalEventType,
    ApprovalPayloadMismatchError,
    ApprovalRequest,
    DurableStep,
    DurableStepStatus,
    ExecutionRunStatus,
    ExecutionRun,
    canonical_payload_hash,
)
from src.repositories.sqlite_durable_execution_repository import (
    SQLiteDurableExecutionRepository,
)
from src.services.approval_service import ApprovalService
from src.services.context_builder import ContextBuilder
from src.services.executor_service import ExecutorService
from src.services.llm_service import LLMService
from src.services.permission_service import PermissionService
from src.services.variable_resolver import VariableResolver
from src.models.tool_result import ToolResult
from src.tools.base_tool import BaseTool
from src.tools.tool_manager import ToolManager


class RecordingApprovalTool(BaseTool):
    def __init__(self) -> None:
        self.calls = []

    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def description(self) -> str:
        return "Records durable approval execution."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["action", "path", "content"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        self.calls.append(kwargs)
        return ToolResult(success=True, tool_name=self.name, output="approved")


class DurableApprovalRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_approved_payload_cannot_authorize_changed_arguments(self):
        repository = await self._repository()
        approval = ApprovalRequest.create(
            approval_id="approval-1",
            execution_id="run-1",
            step_id=1,
            operation_id="operation-1",
            tool="filesystem",
            action="write file",
            arguments={"action": "write_file", "path": "out.txt", "content": "approved"},
            reason="writes a file",
            risk_level="high",
        )
        await repository.request_approval(approval)

        with self.assertRaises(ApprovalPayloadMismatchError):
            await repository.approve(
                approval.execution_id,
                approval.approval_id,
                canonical_payload_hash(
                    "filesystem",
                    "write file",
                    {"action": "write_file", "path": "out.txt", "content": "changed"},
                ),
            )

    async def test_pending_approval_survives_fresh_repository_without_execution(self):
        repository = await self._repository()
        approval = self._approval()
        await repository.request_approval(approval)

        restored = SQLiteDurableExecutionRepository(repository.database_path)
        loaded_approval = await restored.get_approval("run-1", "approval-1")
        loaded_run = await restored.load("run-1")

        self.assertEqual(loaded_approval.event_type, ApprovalEventType.REQUESTED)
        self.assertEqual(loaded_approval.arguments, approval.arguments)
        self.assertEqual(loaded_run.status, ExecutionRunStatus.WAITING_APPROVAL)
        self.assertEqual(loaded_run.steps[0].status, DurableStepStatus.WAITING_APPROVAL)

    async def test_rejection_persists_without_claiming_the_operation(self):
        repository = await self._repository()
        await repository.request_approval(self._approval())

        await repository.reject("run-1", "approval-1")
        loaded = await repository.load("run-1")

        self.assertEqual(loaded.status, ExecutionRunStatus.FAILED)
        self.assertEqual(loaded.steps[0].status, DurableStepStatus.REJECTED)
        self.assertEqual(await repository.operation_events("operation-1"), [])

    async def test_approval_after_restart_executes_frozen_operation_once(self):
        repository = await self._repository()
        await repository.request_approval(self._approval())
        restored = SQLiteDurableExecutionRepository(repository.database_path)
        tool = RecordingApprovalTool()
        manager = ToolManager()
        manager.register(tool)
        executor = ExecutorService(
            llm=LLMService(), context_builder=ContextBuilder(), tool_manager=manager,
            variable_resolver=VariableResolver(), permission_service=PermissionService(),
            durable_repository=restored,
        )
        service = ApprovalService(manager, restored, executor)

        result = await service.approve_durable("run-1", "approval-1")

        self.assertTrue(result.success)
        self.assertEqual(tool.calls, [{"action": "write_file", "path": "out.txt", "content": "approved"}])
        self.assertEqual((await restored.load("run-1")).steps[0].status, DurableStepStatus.COMPLETED)

    def _approval(self):
        return ApprovalRequest.create(
            approval_id="approval-1",
            execution_id="run-1",
            step_id=1,
            operation_id="operation-1",
            tool="filesystem",
            action="write file",
            arguments={"action": "write_file", "path": "out.txt", "content": "approved"},
            reason="writes a file",
            risk_level="high",
        )

    async def _repository(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        repository = SQLiteDurableExecutionRepository(
            Path(directory.name) / "approval.sqlite3"
        )
        arguments = {"action": "write_file", "path": "out.txt", "content": "approved"}
        payload_hash = canonical_payload_hash("filesystem", "write file", arguments)
        await repository.initialize()
        await repository.create_planning_run(
            ExecutionRun(execution_id="run-1", objective="write source")
        )
        await repository.persist_validated_plan(
            "run-1",
            [
                DurableStep(
                    step_id=1,
                    ordinal=0,
                    action="write file",
                    tool="filesystem",
                    arguments=arguments,
                    resolved_arguments=arguments,
                    operation_id="operation-1",
                    payload_hash=payload_hash,
                )
            ],
        )
        return repository


if __name__ == "__main__":
    unittest.main()
