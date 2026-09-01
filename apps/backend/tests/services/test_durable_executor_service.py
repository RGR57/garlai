import tempfile
import unittest
from pathlib import Path

from src.models.execution_state import ExecutionState
from src.models.conversation import ConversationMessage
from src.models.plan import PlanStep
from src.models.tool_result import ToolResult
from src.models.durable_execution import (
    DurableStep,
    DurableStepStatus,
    ExecutionRun,
    ExecutionRunStatus,
    canonical_payload_hash,
)
from src.repositories.sqlite_durable_execution_repository import (
    SQLiteDurableExecutionRepository,
)
from src.services.context_builder import ContextBuilder
from src.services.approval_service import ApprovalService
from src.services.executor_service import ExecutorService
from src.services.llm_providers import FakeLLMProvider
from src.services.llm_service import LLMService
from src.services.permission_service import PermissionService
from src.services.variable_resolver import VariableResolver
from src.tools.base_tool import BaseTool
from src.tools.tool_manager import ToolManager


class RecordingFilesystemTool(BaseTool):
    def __init__(
        self,
        raises: Exception | None = None,
        success: bool = True,
    ) -> None:
        self.calls: list[dict] = []
        self.raises = raises
        self.success = success

    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def description(self) -> str:
        return "Durable executor recording filesystem tool."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["action", "path"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return ToolResult(
            success=self.success,
            tool_name=self.name,
            output="written" if self.success else None,
            metadata={} if self.success else {"error": "read failed"},
        )


class DurableExecutorServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_step_is_not_invoked_again_after_reload(self):
        repository, tool = await self._repository_and_tool(
            status=DurableStepStatus.COMPLETED
        )
        executor = self._executor(repository, tool)

        result = await executor.execute_ready_step(
            "run-1", 1, [], ExecutionState()
        )

        self.assertTrue(result.metadata["durable_skip"])
        self.assertEqual(tool.calls, [])

    async def test_post_intent_exception_becomes_uncertain(self):
        repository, tool = await self._repository_and_tool(
            tool=RecordingFilesystemTool(RuntimeError("connection lost"))
        )
        executor = self._executor(repository, tool)

        result = await executor.execute_ready_step(
            "run-1", 1, [], ExecutionState()
        )

        loaded = await repository.load("run-1")
        self.assertEqual(result.metadata["durable_status"], "uncertain")
        self.assertEqual(loaded.status, ExecutionRunStatus.RECOVERY_REQUIRED)
        self.assertEqual(loaded.steps[0].status, DurableStepStatus.UNCERTAIN)
        self.assertEqual(len(tool.calls), 1)

    async def test_read_only_step_persists_its_completed_outcome(self):
        repository, tool = await self._repository_and_tool(
            action="read_file",
            arguments={"action": "read_file", "path": "out.txt"},
        )
        executor = self._executor(repository, tool)

        result = await executor.execute_ready_step(
            "run-1", 1, [], ExecutionState()
        )

        loaded = await repository.load("run-1")
        self.assertTrue(result.success)
        self.assertEqual(loaded.steps[0].status, DurableStepStatus.COMPLETED)
        self.assertEqual(tool.calls, [{"action": "read_file", "path": "out.txt"}])

    async def test_read_only_step_with_durable_operation_identity_executes(self):
        repository, tool = await self._repository_and_tool(
            action="read_file",
            arguments={"action": "read_file", "path": "out.txt"},
            operation_id="operation-1",
        )
        result = await self._executor(repository, tool).execute_ready_step(
            "run-1", 1, [], ExecutionState()
        )

        self.assertTrue(result.success)
        self.assertEqual(tool.calls, [{"action": "read_file", "path": "out.txt"}])

    async def test_proven_read_only_failure_terminalizes_the_run(self):
        repository, tool = await self._repository_and_tool(
            tool=RecordingFilesystemTool(success=False),
            action="read file",
            arguments={"action": "read_file", "path": "out.txt"},
        )

        result = await self._executor(repository, tool).execute_ready_step(
            "run-1", 1, [], ExecutionState()
        )

        loaded = await repository.load("run-1")
        self.assertFalse(result.success)
        self.assertEqual(loaded.steps[0].status, DurableStepStatus.KNOWN_FAILED)
        self.assertEqual(loaded.status, ExecutionRunStatus.FAILED)
        self.assertIsNone(loaded.next_step_id)

    async def test_dependent_approval_freezes_resolved_arguments_before_requesting_approval(self):
        repository, tool = await self._repository_and_tool(
            action="write source",
            arguments={
                "action": "write_file",
                "path": "src/out.py",
                "content": "{{step1}}",
            },
            operation_id="operation-1",
            resolved_arguments=None,
        )
        executor = self._executor(repository, tool)

        result = await executor.execute_ready_step(
            "run-1",
            1,
            [],
            ExecutionState(variables={"step1": "frozen content"}),
        )

        self.assertFalse(result.success)
        self.assertIn("Approval required", result.error)
        approval = await repository.get_pending_approval("run-1")
        step = (await repository.load("run-1")).steps[0]
        self.assertEqual(
            approval.arguments,
            {
                "action": "write_file",
                "path": "src/out.py",
                "content": "frozen content",
            },
        )
        self.assertEqual(step.resolved_arguments, approval.arguments)
        self.assertEqual(step.payload_hash, approval.payload_hash)
        self.assertEqual(tool.calls, [])

        approved = await ApprovalService(
            executor.tool_manager,
            repository,
            executor,
        ).approve_durable(
            "run-1",
            approval.approval_id,
            ExecutionState(variables={"step1": "tampered content"}),
        )

        self.assertTrue(approved.success)
        self.assertEqual(tool.calls, [approval.arguments])

    async def test_persisted_llm_step_executes_and_records_result(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        repository = SQLiteDurableExecutionRepository(
            Path(directory.name) / "llm.sqlite3"
        )
        await repository.initialize()
        await repository.create_planning_run(
            ExecutionRun(execution_id="run-llm", objective="answer a question")
        )
        await repository.persist_validated_plan(
            "run-llm",
            [
                DurableStep(
                    step_id=1,
                    ordinal=0,
                    action="answer",
                    tool=None,
                    plan_input="Reply with the answer.",
                )
            ],
        )
        executor = self._executor(repository, RecordingFilesystemTool())
        executor.llm = LLMService(provider=FakeLLMProvider())

        result = await executor.execute_ready_step(
            "run-llm",
            1,
            [ConversationMessage(role="user", content="What is 2 + 2?")],
            ExecutionState(),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, "Hey! GARL is running.")
        loaded = await repository.load("run-llm")
        self.assertEqual(loaded.steps[0].status, DurableStepStatus.COMPLETED)
        self.assertEqual(loaded.status, ExecutionRunStatus.COMPLETED)

    async def _repository_and_tool(
        self,
        *,
        status: DurableStepStatus = DurableStepStatus.PENDING,
        tool: RecordingFilesystemTool | None = None,
        action: str = "write file",
        arguments: dict | None = None,
        operation_id: str | None = None,
        resolved_arguments: dict | None | object = ...,
    ):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        repository = SQLiteDurableExecutionRepository(
            Path(directory.name) / "executor.sqlite3"
        )
        arguments = arguments or {
            "action": "write_file", "path": "out.txt", "content": "x"
        }
        if resolved_arguments is ...:
            resolved_arguments = arguments
        payload_hash = canonical_payload_hash("filesystem", action, arguments)
        await repository.initialize()
        await repository.create_planning_run(
            ExecutionRun(execution_id="run-1", objective="write a file")
        )
        await repository.persist_validated_plan(
            "run-1",
            [
                DurableStep(
                    step_id=1,
                    ordinal=0,
                    action=action,
                    tool="filesystem",
                    arguments=arguments,
                    resolved_arguments=resolved_arguments,
                    status=status,
                    operation_id=(
                        operation_id
                        if operation_id is not None
                        else "operation-1" if arguments["action"] == "write_file" else None
                    ),
                    payload_hash=payload_hash if arguments["action"] == "write_file" else None,
                    result={"output": "written"}
                    if status is DurableStepStatus.COMPLETED
                    else None,
                )
            ],
        )
        return repository, tool or RecordingFilesystemTool()

    def _executor(self, repository, tool):
        manager = ToolManager()
        manager.register(tool)
        return ExecutorService(
            llm=LLMService(),
            context_builder=ContextBuilder(),
            tool_manager=manager,
            variable_resolver=VariableResolver(),
            permission_service=PermissionService(),
            durable_repository=repository,
        )


if __name__ == "__main__":
    unittest.main()
