import unittest

from src.models.durable_execution import (
    canonical_payload_hash,
    DurableStateCorruptionError,
    DurableStep,
    DurableStepStatus,
    ExecutionRun,
)

from src.repositories.sqlite_durable_execution_repository import (
    SQLiteDurableExecutionRepository,
)


class SQLiteDurableExecutionRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_is_idempotent_and_enables_foreign_keys(self):
        database_path = self._tmp_path("durable.sqlite3")
        repository = SQLiteDurableExecutionRepository(database_path)

        await repository.initialize()
        await repository.initialize()

        self.assertEqual(await repository.schema_versions(), [1])
        self.assertTrue(await repository.foreign_keys_enabled())
        self.assertEqual(await repository.journal_mode(), "wal")

    async def test_fresh_repository_loads_persisted_run_and_completed_step(self):
        path = self._tmp_path("restart.sqlite3")
        first = SQLiteDurableExecutionRepository(path)
        await first.initialize()
        await first.create_planning_run(
            ExecutionRun(
                execution_id="run-1",
                objective="prepare a report",
                execution_context={"source": "chat"},
                variables={"step1": "first output"},
            )
        )
        await first.persist_validated_plan(
            "run-1",
            [
                DurableStep(
                    step_id=1,
                    ordinal=0,
                    action="inspect source",
                    tool="terminal",
                    arguments={"query": "echo first"},
                    status=DurableStepStatus.COMPLETED,
                    result={"output": "first output"},
                    artifact={"reference": "artifact-1"},
                )
            ],
        )

        second = SQLiteDurableExecutionRepository(path)
        loaded = await second.load("run-1")

        self.assertEqual(loaded.objective, "prepare a report")
        self.assertEqual(loaded.variables, {"step1": "first output"})
        self.assertEqual(loaded.steps[0].status, DurableStepStatus.COMPLETED)
        self.assertEqual(loaded.steps[0].result, {"output": "first output"})

    async def test_load_rejects_invalid_constrained_json(self):
        repository = SQLiteDurableExecutionRepository(
            self._tmp_path("corrupt.sqlite3")
        )
        await repository.initialize()
        await repository.insert_invalid_json_for_test("run-corrupt")

        with self.assertRaises(DurableStateCorruptionError):
            await repository.load("run-corrupt")

    async def test_execution_context_patch_deep_merges_and_survives_fresh_repository(self):
        path = self._tmp_path("context-patch.sqlite3")
        first = SQLiteDurableExecutionRepository(path)
        await first.initialize()
        await first.create_planning_run(
            ExecutionRun(
                execution_id="run-context",
                objective="inspect marketplace",
                execution_context={
                    "source": "chat",
                    "browser": {"last_verified_url": "https://market.example/pricing"},
                },
            )
        )

        await first.patch_execution_context(
            "run-context",
            {
                "browser": {
                    "session_id": "browser-run-context",
                    "latest_observation": {"observation_id": "obs-1"},
                }
            },
        )

        loaded = await SQLiteDurableExecutionRepository(path).load("run-context")

        self.assertEqual(
            loaded.execution_context,
            {
                "source": "chat",
                "browser": {
                    "last_verified_url": "https://market.example/pricing",
                    "session_id": "browser-run-context",
                    "latest_observation": {"observation_id": "obs-1"},
                },
            },
        )

    async def test_read_only_outcome_commits_browser_context_with_the_completed_step(self):
        path = self._tmp_path("context-outcome.sqlite3")
        repository = SQLiteDurableExecutionRepository(path)
        await repository.initialize()
        await repository.create_planning_run(
            ExecutionRun(execution_id="run-outcome", objective="observe pricing")
        )
        await repository.persist_validated_plan(
            "run-outcome",
            [
                DurableStep(
                    step_id=1,
                    ordinal=0,
                    action="observe pricing",
                    tool="browser_observe",
                    arguments={},
                )
            ],
        )
        self.assertTrue(await repository.claim_read_only_step("run-outcome", 1))

        await repository.record_read_only_outcome(
            "run-outcome",
            1,
            DurableStepStatus.COMPLETED,
            result={"output": {"observation_id": "obs-1"}},
            execution_context_patch={
                "browser": {"latest_observation": {"observation_id": "obs-1"}}
            },
        )

        loaded = await SQLiteDurableExecutionRepository(path).load("run-outcome")

        self.assertEqual(loaded.steps[0].status, DurableStepStatus.COMPLETED)
        self.assertEqual(
            loaded.execution_context["browser"]["latest_observation"],
            {"observation_id": "obs-1"},
        )

    async def test_operation_outcome_commits_browser_context_with_the_completed_step(self):
        path = self._tmp_path("operation-context-outcome.sqlite3")
        repository = SQLiteDurableExecutionRepository(path)
        await repository.initialize()
        await repository.create_planning_run(
            ExecutionRun(execution_id="run-operation", objective="select plan")
        )
        arguments = {"target": "pro"}
        payload_hash = canonical_payload_hash("browser_select", "choose plan", arguments)
        await repository.persist_validated_plan(
            "run-operation",
            [
                DurableStep(
                    step_id=1,
                    ordinal=0,
                    action="choose plan",
                    tool="browser_select",
                    arguments=arguments,
                    operation_id="operation-1",
                    payload_hash=payload_hash,
                )
            ],
        )
        claim = await repository.claim_operation(
            "run-operation", 1, "operation-1", payload_hash
        )
        self.assertTrue(claim.granted)

        await repository.record_operation_outcome(
            claim,
            DurableStepStatus.COMPLETED,
            result={"output": "selected"},
            execution_context_patch={"browser": {"selected_plan": "pro"}},
        )

        loaded = await SQLiteDurableExecutionRepository(path).load("run-operation")

        self.assertEqual(loaded.steps[0].status, DurableStepStatus.COMPLETED)
        self.assertEqual(loaded.execution_context["browser"]["selected_plan"], "pro")

    def _tmp_path(self, filename: str):
        import tempfile
        from pathlib import Path

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name) / filename


if __name__ == "__main__":
    unittest.main()
