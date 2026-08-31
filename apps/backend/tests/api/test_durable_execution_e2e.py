import tempfile
import unittest
from pathlib import Path

from src.models.durable_execution import (
    DurableStep,
    ExecutionRun,
    ExecutionRunStatus,
    canonical_payload_hash,
)
from src.models.execution_state import ExecutionState
from src.models.tool_result import ToolResult
from src.repositories.sqlite_durable_execution_repository import (
    SQLiteDurableExecutionRepository,
)
from src.services.context_builder import ContextBuilder
from src.services.executor_service import ExecutorService
from src.services.llm_service import LLMService
from src.services.permission_service import PermissionService
from src.services.recovery_service import RecoveryService
from src.services.variable_resolver import VariableResolver
from src.tools.base_tool import BaseTool
from src.tools.tool_manager import ToolManager


class RecordingFilesystemTool(BaseTool):
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    @property
    def name(self):
        return "filesystem"

    @property
    def description(self):
        return "Records durable digital work."

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {"action": {"type": "string"}, "path": {"type": "string"}},
            "required": ["action", "path"],
        }

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return ToolResult(success=True, tool_name=self.name, output=self.outputs[len(self.calls) - 1])


class DurableExecutionMissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_multistep_objective_resumes_after_fresh_graph_without_duplicate_work(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "mission.sqlite3"
        first_repository = SQLiteDurableExecutionRepository(path)
        await first_repository.initialize()
        await first_repository.create_planning_run(ExecutionRun(execution_id="run-1", objective="prepare a report"))
        await first_repository.persist_validated_plan(
            "run-1",
            [
                DurableStep(step_id=1, ordinal=0, action="read source", tool="filesystem", arguments={"action": "read_file", "path": "source.txt"}),
                DurableStep(step_id=2, ordinal=1, action="read derived source", tool="filesystem", arguments={"action": "read_file", "path": "{{step1}}"}),
            ],
        )
        first_tool = RecordingFilesystemTool(["source output"])
        await self._executor(first_repository, first_tool).execute_ready_step("run-1", 1, [], ExecutionState())

        second_repository = SQLiteDurableExecutionRepository(path)
        decision = await RecoveryService(second_repository).prepare_resume("run-1")
        second_tool = RecordingFilesystemTool(["report output"])
        result = await self._executor(second_repository, second_tool).execute_ready_step(
            "run-1", decision.next_step_id, [], decision.execution_state
        )

        self.assertTrue(result.success)
        self.assertEqual(first_tool.calls, [{"action": "read_file", "path": "source.txt"}])
        self.assertEqual(second_tool.calls, [{"action": "read_file", "path": "source output"}])
        self.assertEqual((await second_repository.load("run-1")).status, ExecutionRunStatus.COMPLETED)

    async def test_orphaned_consequential_intent_stops_fresh_graph_without_second_call(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "uncertain.sqlite3"
        repository = SQLiteDurableExecutionRepository(path)
        arguments = {"action": "write_file", "path": "out.txt"}
        payload_hash = canonical_payload_hash("filesystem", "write file", arguments)
        await repository.initialize()
        await repository.create_planning_run(ExecutionRun(execution_id="run-1", objective="write report"))
        await repository.persist_validated_plan("run-1", [DurableStep(step_id=1, ordinal=0, action="write file", tool="filesystem", arguments=arguments, operation_id="operation-1", payload_hash=payload_hash)])
        await repository.claim_operation("run-1", 1, "operation-1", payload_hash)

        fresh_tool = RecordingFilesystemTool(["should not run"])
        decision = await RecoveryService(SQLiteDurableExecutionRepository(path)).prepare_resume("run-1")

        self.assertEqual(decision.status, ExecutionRunStatus.RECOVERY_REQUIRED)
        self.assertFalse(decision.may_execute)
        self.assertEqual(fresh_tool.calls, [])

    @staticmethod
    def _executor(repository, tool):
        manager = ToolManager()
        manager.register(tool)
        return ExecutorService(LLMService(), ContextBuilder(), manager, VariableResolver(), PermissionService(), repository)
