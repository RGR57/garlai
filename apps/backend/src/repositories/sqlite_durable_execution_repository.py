from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from src.models.durable_execution import DurableStep, ExecutionRun
from src.repositories.durable_execution_repository import DurableExecutionRepository


T = TypeVar("T")


class SQLiteDurableExecutionRepository(DurableExecutionRepository):
    """SQLite persistence for the durable execution aggregate and journals."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        database_path: Path,
        busy_timeout_ms: int = 5000,
    ) -> None:
        if busy_timeout_ms <= 0:
            raise ValueError("busy_timeout_ms must be positive")

        self.database_path = Path(database_path)
        self.busy_timeout_ms = busy_timeout_ms

    async def initialize(self) -> None:
        await self._run(self._initialize)

    async def schema_versions(self) -> list[int]:
        return await self._run(self._schema_versions)

    async def foreign_keys_enabled(self) -> bool:
        return await self._run(self._foreign_keys_enabled)

    async def journal_mode(self) -> str:
        return await self._run(self._journal_mode)

    async def create_planning_run(self, run: ExecutionRun) -> None:
        raise NotImplementedError("Aggregate persistence is added in Task 3.")

    async def persist_validated_plan(
        self,
        execution_id: str,
        steps: list[DurableStep],
    ) -> None:
        raise NotImplementedError("Aggregate persistence is added in Task 3.")

    async def load(self, execution_id: str) -> ExecutionRun:
        raise NotImplementedError("Aggregate persistence is added in Task 3.")

    async def list_recoverable(self) -> list[ExecutionRun]:
        raise NotImplementedError("Aggregate loading is added in Task 3.")

    async def delete_for_test(self, execution_id: str) -> None:
        raise NotImplementedError("Aggregate persistence is added in Task 3.")

    async def _run(self, operation: Callable[[], T]) -> T:
        return await asyncio.to_thread(operation)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.database_path,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN EXCLUSIVE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations"
                )
            }
            if self.SCHEMA_VERSION not in applied:
                for statement in _MIGRATION_1_STATEMENTS:
                    connection.execute(statement)
                connection.execute(
                    """
                    INSERT INTO schema_migrations (version, applied_at)
                    VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    """,
                    (self.SCHEMA_VERSION,),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _schema_versions(self) -> list[int]:
        connection = self._connect()
        try:
            return [
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            ]
        finally:
            connection.close()

    def _foreign_keys_enabled(self) -> bool:
        connection = self._connect()
        try:
            return connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            connection.close()

    def _journal_mode(self) -> str:
        connection = self._connect()
        try:
            return str(connection.execute("PRAGMA journal_mode").fetchone()[0])
        finally:
            connection.close()


_MIGRATION_1_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS execution_runs (
        execution_id TEXT PRIMARY KEY,
        objective TEXT NOT NULL,
        conversation_id TEXT,
        status TEXT NOT NULL,
        plan_version INTEGER NOT NULL,
        current_step_id INTEGER,
        next_step_id INTEGER,
        attempt_count INTEGER NOT NULL,
        iteration_count INTEGER NOT NULL,
        final_response TEXT,
        execution_context_json TEXT NOT NULL,
        variables_json TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_steps (
        execution_id TEXT NOT NULL,
        step_id INTEGER NOT NULL,
        ordinal INTEGER NOT NULL,
        action TEXT NOT NULL,
        tool TEXT,
        plan_input TEXT NOT NULL,
        arguments_json TEXT NOT NULL,
        resolved_arguments_json TEXT,
        classification TEXT,
        status TEXT NOT NULL,
        operation_id TEXT UNIQUE,
        payload_hash TEXT,
        attempt_count INTEGER NOT NULL,
        result_json TEXT,
        error_json TEXT,
        artifact_json TEXT,
        metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (execution_id, step_id),
        UNIQUE (execution_id, ordinal),
        FOREIGN KEY (execution_id)
            REFERENCES execution_runs (execution_id)
            ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS operation_journal (
        operation_event_id TEXT PRIMARY KEY,
        execution_id TEXT NOT NULL,
        step_id INTEGER NOT NULL,
        operation_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        attempt_id TEXT,
        payload_hash TEXT NOT NULL,
        fact_json TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        UNIQUE (operation_id, event_type),
        FOREIGN KEY (execution_id, step_id)
            REFERENCES execution_steps (execution_id, step_id)
            ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS approval_journal (
        approval_event_id TEXT PRIMARY KEY,
        approval_id TEXT NOT NULL,
        execution_id TEXT NOT NULL,
        step_id INTEGER NOT NULL,
        operation_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        canonical_payload_json TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        UNIQUE (approval_id, event_type),
        FOREIGN KEY (execution_id, step_id)
            REFERENCES execution_steps (execution_id, step_id)
            ON DELETE CASCADE
    )
    """,
)
