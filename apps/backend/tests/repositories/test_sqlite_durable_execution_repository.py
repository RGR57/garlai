import unittest

from src.models.durable_execution import (
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

    def _tmp_path(self, filename: str):
        import tempfile
        from pathlib import Path

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name) / filename


if __name__ == "__main__":
    unittest.main()
