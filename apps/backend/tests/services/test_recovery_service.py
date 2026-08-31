import tempfile
import unittest
from pathlib import Path

from src.models.durable_execution import (
    ApprovalRequest,
    DurableStep,
    DurableStepStatus,
    ExecutionRun,
    ExecutionRunStatus,
    OperationEventType,
    canonical_payload_hash,
)
from src.models.plan import ExecutionPlan, PlanStep
from src.repositories.sqlite_durable_execution_repository import (
    SQLiteDurableExecutionRepository,
)
from src.services.recovery_service import RecoveryService
from src.services.durable_execution_service import DurableExecutionService


class CompletionWinsRecoveryRepository:
    """Simulates an in-flight worker committing before recovery can stop it."""

    def __init__(self, repository, claim) -> None:
        self.repository = repository
        self.claim = claim
        self.completion_recorded = False

    async def load(self, execution_id):
        return await self.repository.load(execution_id)

    async def list_orphaned_operations(self, execution_id):
        return await self.repository.list_orphaned_operations(execution_id)

    async def mark_operation_uncertain(
        self, execution_id, step_id, operation_id, reason
    ):
        if not self.completion_recorded:
            self.completion_recorded = True
            await self.repository.record_operation_outcome(
                self.claim,
                DurableStepStatus.COMPLETED,
                result={"output": "confirmed concurrently"},
            )
        await self.repository.mark_operation_uncertain(
            execution_id, step_id, operation_id, reason
        )


class RecoveryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_validated_plan_is_persisted_once_and_restart_uses_that_plan(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database_path = Path(directory.name) / "coordinator.sqlite3"
        repository = SQLiteDurableExecutionRepository(database_path)
        await repository.initialize()
        service = DurableExecutionService(repository)

        run = await service.start(
            objective="read a release note",
            execution_context={"messages": [{"role": "user", "content": "note"}]},
            execution_id="run-1",
        )
        persisted = await service.persist_validated_plan(
            run.execution_id,
            ExecutionPlan(
                steps=[
                    PlanStep(
                        id=7,
                        action="read release note",
                        tool="filesystem",
                        input="Read the note.",
                        arguments={"action": "read_file", "path": "release.md"},
                    )
                ]
            ),
        )

        restored = SQLiteDurableExecutionRepository(database_path)
        decision = await RecoveryService(restored).prepare_resume("run-1")

        self.assertEqual(persisted.status, ExecutionRunStatus.RUNNING)
        self.assertEqual(decision.next_step_id, 7)
        self.assertEqual(decision.run.steps[0].action, "read release note")
        with self.assertRaises(ValueError):
            await service.persist_validated_plan(
                "run-1",
                ExecutionPlan(
                    steps=[
                        PlanStep(
                            id=8,
                            action="silently replace the plan",
                            tool=None,
                        )
                    ]
                ),
            )

    async def test_orphaned_intent_becomes_uncertain_without_resuming_work(self):
        repository, payload_hash = await self._repository_with_plan()
        claim = await repository.claim_operation(
            "run-1", 1, "operation-1", payload_hash
        )
        self.assertTrue(claim.granted)

        restored = SQLiteDurableExecutionRepository(repository.database_path)
        decision = await RecoveryService(restored).prepare_resume("run-1")
        recovered = await restored.load("run-1")

        self.assertEqual(decision.status, ExecutionRunStatus.RECOVERY_REQUIRED)
        self.assertFalse(decision.may_execute)
        self.assertIsNone(decision.next_step_id)
        self.assertEqual(recovered.status, ExecutionRunStatus.RECOVERY_REQUIRED)
        self.assertEqual(recovered.steps[0].status, DurableStepStatus.UNCERTAIN)
        self.assertEqual(
            await restored.operation_events("operation-1"),
            [OperationEventType.INTENT_RECORDED, OperationEventType.UNCERTAIN],
        )

    async def test_recovery_honors_a_terminal_outcome_that_wins_the_race(self):
        repository, payload_hash = await self._repository_with_plan()
        claim = await repository.claim_operation(
            "run-1", 1, "operation-1", payload_hash
        )
        self.assertTrue(claim.granted)

        decision = await RecoveryService(
            CompletionWinsRecoveryRepository(repository, claim)
        ).prepare_resume("run-1")
        recovered = await repository.load("run-1")

        self.assertEqual(decision.status, ExecutionRunStatus.RUNNING)
        self.assertFalse(decision.may_execute)
        self.assertEqual(recovered.steps[0].status, DurableStepStatus.COMPLETED)
        self.assertEqual(
            await repository.operation_events("operation-1"),
            [OperationEventType.INTENT_RECORDED, OperationEventType.COMPLETED],
        )

    async def test_completed_outputs_restore_and_next_pending_step_is_selected(self):
        repository = await self._repository_with_completed_predecessor()

        restored = SQLiteDurableExecutionRepository(repository.database_path)
        decision = await RecoveryService(restored).prepare_resume("run-1")

        self.assertTrue(decision.may_execute)
        self.assertEqual(decision.next_step_id, 2)
        self.assertEqual(decision.execution_state.current_step, 2)
        self.assertEqual(decision.execution_state.variables["step1"], "first output")
        self.assertEqual(decision.execution_state.history[0].output, "first output")
        self.assertEqual(
            decision.execution_state.history[0].metadata["artifact"],
            {"reference": "artifact-1"},
        )
        self.assertEqual((await restored.load("run-1")).steps[0].status, DurableStepStatus.COMPLETED)

    async def test_waiting_approval_remains_paused_with_frozen_identity(self):
        repository, _ = await self._repository_with_plan()
        approval = ApprovalRequest.create(
            approval_id="approval-1",
            execution_id="run-1",
            step_id=1,
            operation_id="operation-1",
            tool="filesystem",
            action="write file",
            arguments={"action": "write_file", "path": "out.txt", "content": "x"},
            reason="writes a file",
            risk_level="high",
        )
        await repository.request_approval(approval)

        restored = SQLiteDurableExecutionRepository(repository.database_path)
        decision = await RecoveryService(restored).prepare_resume("run-1")

        self.assertEqual(decision.status, ExecutionRunStatus.WAITING_APPROVAL)
        self.assertFalse(decision.may_execute)
        self.assertEqual(decision.pending_approval.approval_id, "approval-1")
        self.assertEqual(decision.pending_approval.execution_id, "run-1")
        self.assertEqual(decision.pending_approval.arguments, approval.arguments)
        self.assertEqual(await restored.operation_events("operation-1"), [])

    async def test_planning_recovery_preserves_objective_and_execution_context(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database_path = Path(directory.name) / "planning.sqlite3"
        repository = SQLiteDurableExecutionRepository(database_path)
        await repository.initialize()
        await repository.create_planning_run(
            ExecutionRun(
                execution_id="run-1",
                objective="summarize the release notes",
                execution_context={"messages": [{"role": "user", "content": "notes"}]},
            )
        )

        restored = SQLiteDurableExecutionRepository(database_path)
        decision = await RecoveryService(restored).prepare_resume("run-1")

        self.assertEqual(decision.status, ExecutionRunStatus.PLANNING)
        self.assertTrue(decision.planning_required)
        self.assertFalse(decision.may_execute)
        self.assertEqual(decision.run.objective, "summarize the release notes")
        self.assertEqual(
            decision.run.execution_context,
            {"messages": [{"role": "user", "content": "notes"}]},
        )

    async def _repository_with_plan(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        repository = SQLiteDurableExecutionRepository(
            Path(directory.name) / "recovery.sqlite3"
        )
        arguments = {"action": "write_file", "path": "out.txt", "content": "x"}
        payload_hash = canonical_payload_hash("filesystem", "write file", arguments)
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
                    action="write file",
                    tool="filesystem",
                    arguments=arguments,
                    resolved_arguments=arguments,
                    operation_id="operation-1",
                    payload_hash=payload_hash,
                )
            ],
        )
        return repository, payload_hash

    async def _repository_with_completed_predecessor(self):
        repository, _ = await self._repository_with_plan()
        arguments = {"action": "write_file", "path": "out.txt", "content": "x"}
        payload_hash = canonical_payload_hash("filesystem", "write file", arguments)
        await repository.delete_for_test("run-1")
        await repository.create_planning_run(
            ExecutionRun(execution_id="run-1", objective="finish three steps")
        )
        await repository.persist_validated_plan(
            "run-1",
            [
                DurableStep(
                    step_id=1,
                    ordinal=0,
                    action="write first result",
                    tool="filesystem",
                    arguments=arguments,
                    resolved_arguments=arguments,
                    status=DurableStepStatus.COMPLETED,
                    operation_id="operation-1",
                    payload_hash=payload_hash,
                    result={"output": "first output"},
                    artifact={"reference": "artifact-1"},
                ),
                DurableStep(
                    step_id=2,
                    ordinal=1,
                    action="read second input",
                    tool="filesystem",
                    arguments={"action": "read_file", "path": "out.txt"},
                ),
                DurableStep(
                    step_id=3,
                    ordinal=2,
                    action="read third input",
                    tool="filesystem",
                    arguments={"action": "read_file", "path": "out.txt"},
                ),
            ],
        )
        return repository


if __name__ == "__main__":
    unittest.main()
