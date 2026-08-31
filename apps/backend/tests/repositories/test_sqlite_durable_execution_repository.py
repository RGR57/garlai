import unittest

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

    def _tmp_path(self, filename: str):
        import tempfile
        from pathlib import Path

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name) / filename


if __name__ == "__main__":
    unittest.main()
