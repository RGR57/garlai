import asyncio
import tempfile
import unittest
from pathlib import Path

from src.models.durable_execution import (
    DurableStep,
    DurableStepStatus,
    ExecutionRunStatus,
    ExecutionRun,
    OperationEventType,
    canonical_payload_hash,
)
from src.repositories.sqlite_durable_execution_repository import (
    SQLiteDurableExecutionRepository,
)


class OperationClaimTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_one_concurrent_caller_claims_consequential_operation(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        repository = SQLiteDurableExecutionRepository(
            Path(directory.name) / "claims.sqlite3"
        )
        payload_hash = canonical_payload_hash(
            "filesystem",
            "write_file",
            {"path": "out.txt", "content": "x"},
        )
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
                    arguments={"path": "out.txt", "content": "x"},
                    operation_id="operation-1",
                    payload_hash=payload_hash,
                )
            ],
        )

        first, second = await asyncio.gather(
            repository.claim_operation(
                "run-1", 1, "operation-1", payload_hash
            ),
            repository.claim_operation(
                "run-1", 1, "operation-1", payload_hash
            ),
        )

        self.assertEqual(sorted([first.granted, second.granted]), [False, True])
        self.assertEqual(
            await repository.operation_events("operation-1"),
            [OperationEventType.INTENT_RECORDED],
        )

    async def test_terminal_outcome_is_persisted_and_conflicting_rewrite_is_rejected(self):
        repository, payload_hash = await self._repository_with_operation()
        claim = await repository.claim_operation(
            "run-1", 1, "operation-1", payload_hash
        )

        await repository.record_operation_outcome(
            claim,
            DurableStepStatus.COMPLETED,
            result={"output": "written"},
        )
        loaded = await repository.load("run-1")

        self.assertEqual(loaded.steps[0].status, DurableStepStatus.COMPLETED)
        self.assertEqual(loaded.steps[0].result, {"output": "written"})
        self.assertEqual(
            await repository.operation_events("operation-1"),
            [
                OperationEventType.INTENT_RECORDED,
                OperationEventType.COMPLETED,
            ],
        )
        await repository.record_operation_outcome(
            claim,
            DurableStepStatus.COMPLETED,
            result={"output": "written"},
        )
        self.assertEqual(
            await repository.operation_events("operation-1"),
            [
                OperationEventType.INTENT_RECORDED,
                OperationEventType.COMPLETED,
            ],
        )
        with self.assertRaises(ValueError):
            await repository.record_operation_outcome(
                claim,
                DurableStepStatus.KNOWN_FAILED,
                error={"message": "conflicting failure"},
            )

    async def test_post_intent_uncertainty_persists_and_cannot_be_claimed_again(self):
        repository, payload_hash = await self._repository_with_operation()
        claim = await repository.claim_operation(
            "run-1", 1, "operation-1", payload_hash
        )
        self.assertTrue(claim.granted)

        await repository.mark_operation_uncertain(
            "run-1",
            1,
            "operation-1",
            "Invocation outcome could not be proven.",
        )

        loaded = await repository.load("run-1")
        second_claim = await repository.claim_operation(
            "run-1", 1, "operation-1", payload_hash
        )

        self.assertEqual(loaded.status, ExecutionRunStatus.RECOVERY_REQUIRED)
        self.assertEqual(loaded.steps[0].status, DurableStepStatus.UNCERTAIN)
        self.assertFalse(second_claim.granted)
        self.assertEqual(
            await repository.operation_events("operation-1"),
            [
                OperationEventType.INTENT_RECORDED,
                OperationEventType.UNCERTAIN,
            ],
        )

    async def _repository_with_operation(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        repository = SQLiteDurableExecutionRepository(
            Path(directory.name) / "operation.sqlite3"
        )
        payload_hash = canonical_payload_hash(
            "filesystem",
            "write_file",
            {"path": "out.txt", "content": "x"},
        )
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
                    arguments={"path": "out.txt", "content": "x"},
                    operation_id="operation-1",
                    payload_hash=payload_hash,
                )
            ],
        )
        return repository, payload_hash


if __name__ == "__main__":
    unittest.main()
