from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from src.models.durable_execution import (
    DurableStateCorruptionError,
    DurableStep,
    DurableStepStatus,
    ExecutionRun,
    ExecutionRunStatus,
)
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
        await self._run(lambda: self._create_planning_run(run))

    async def persist_validated_plan(
        self,
        execution_id: str,
        steps: list[DurableStep],
    ) -> None:
        await self._run(
            lambda: self._persist_validated_plan(execution_id, steps)
        )

    async def load(self, execution_id: str) -> ExecutionRun:
        return await self._run(lambda: self._load(execution_id))

    async def list_recoverable(self) -> list[ExecutionRun]:
        return await self._run(self._list_recoverable)

    async def delete_for_test(self, execution_id: str) -> None:
        await self._run(lambda: self._delete_for_test(execution_id))

    async def insert_invalid_json_for_test(self, execution_id: str) -> None:
        await self._run(lambda: self._insert_invalid_json_for_test(execution_id))

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

    def _create_planning_run(self, run: ExecutionRun) -> None:
        if run.status is not ExecutionRunStatus.PLANNING:
            raise ValueError("A newly created durable run must be planning.")
        if run.steps:
            raise ValueError("A planning run cannot contain a validated plan.")

        now = _now()
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO execution_runs (
                    execution_id, objective, conversation_id, status, plan_version,
                    current_step_id, next_step_id, attempt_count, iteration_count,
                    final_response, execution_context_json, variables_json,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.execution_id,
                    run.objective,
                    run.conversation_id,
                    run.status.value,
                    run.plan_version,
                    run.current_step_id,
                    run.next_step_id,
                    run.attempt_count,
                    run.iteration_count,
                    run.final_response,
                    _encode_json(run.execution_context),
                    _encode_json(run.variables),
                    _encode_json(run.metadata),
                    _encode_time(run.created_at) or now,
                    _encode_time(run.updated_at) or now,
                ),
            )
        finally:
            connection.close()

    def _persist_validated_plan(
        self,
        execution_id: str,
        steps: list[DurableStep],
    ) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE execution_runs
                SET status = ?, next_step_id = ?, updated_at = ?
                WHERE execution_id = ? AND status = ?
                """,
                (
                    ExecutionRunStatus.RUNNING.value,
                    steps[0].step_id if steps else None,
                    _now(),
                    execution_id,
                    ExecutionRunStatus.PLANNING.value,
                ),
            ).rowcount
            if updated != 1:
                raise ValueError("Validated plans may only be persisted once.")
            for step in steps:
                self._insert_step(connection, execution_id, step)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _insert_step(
        self,
        connection: sqlite3.Connection,
        execution_id: str,
        step: DurableStep,
    ) -> None:
        now = _now()
        connection.execute(
            """
            INSERT INTO execution_steps (
                execution_id, step_id, ordinal, action, tool, plan_input,
                arguments_json, resolved_arguments_json, classification, status,
                operation_id, payload_hash, attempt_count, result_json, error_json,
                artifact_json, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id,
                step.step_id,
                step.ordinal,
                step.action,
                step.tool,
                step.plan_input,
                _encode_json(step.arguments),
                _encode_optional_json(step.resolved_arguments),
                step.classification,
                step.status.value,
                step.operation_id,
                step.payload_hash,
                step.attempt_count,
                _encode_optional_json(step.result),
                _encode_optional_json(step.error),
                _encode_optional_json(step.artifact),
                _encode_json(step.metadata),
                _encode_time(step.created_at) or now,
                _encode_time(step.updated_at) or now,
            ),
        )

    def _load(self, execution_id: str) -> ExecutionRun:
        connection = self._connect()
        try:
            run_row = connection.execute(
                "SELECT * FROM execution_runs WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if run_row is None:
                raise KeyError(f"Unknown execution: {execution_id}")
            step_rows = connection.execute(
                """
                SELECT * FROM execution_steps
                WHERE execution_id = ? ORDER BY ordinal
                """,
                (execution_id,),
            ).fetchall()
            return _decode_run(run_row, step_rows)
        finally:
            connection.close()

    def _list_recoverable(self) -> list[ExecutionRun]:
        connection = self._connect()
        try:
            identifiers = [
                row["execution_id"]
                for row in connection.execute(
                    """
                    SELECT execution_id FROM execution_runs
                    WHERE status IN (?, ?, ?, ?)
                    ORDER BY created_at
                    """,
                    tuple(
                        status.value
                        for status in (
                            ExecutionRunStatus.PLANNING,
                            ExecutionRunStatus.RUNNING,
                            ExecutionRunStatus.WAITING_APPROVAL,
                            ExecutionRunStatus.RECOVERY_REQUIRED,
                        )
                    ),
                )
            ]
        finally:
            connection.close()
        return [self._load(execution_id) for execution_id in identifiers]

    def _delete_for_test(self, execution_id: str) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "DELETE FROM execution_runs WHERE execution_id = ?",
                (execution_id,),
            )
        finally:
            connection.close()

    def _insert_invalid_json_for_test(self, execution_id: str) -> None:
        self._create_planning_run(
            ExecutionRun(execution_id=execution_id, objective="corrupt test")
        )
        connection = self._connect()
        try:
            connection.execute(
                "UPDATE execution_runs SET variables_json = ? WHERE execution_id = ?",
                ("[]", execution_id),
            )
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


def _encode_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Durable values must be constrained JSON") from exc


def _encode_optional_json(value: object | None) -> str | None:
    return None if value is None else _encode_json(value)


def _decode_mapping(raw: str | None, field_name: str) -> dict:
    if raw is None:
        raise DurableStateCorruptionError(f"{field_name} is missing")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DurableStateCorruptionError(
            f"{field_name} contains invalid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise DurableStateCorruptionError(f"{field_name} must decode to an object")
    return value


def _decode_optional_mapping(raw: str | None, field_name: str) -> dict | None:
    return None if raw is None else _decode_mapping(raw, field_name)


def _decode_run(
    run_row: sqlite3.Row,
    step_rows: list[sqlite3.Row],
) -> ExecutionRun:
    try:
        steps = [
            DurableStep(
                step_id=row["step_id"],
                ordinal=row["ordinal"],
                action=row["action"],
                tool=row["tool"],
                plan_input=row["plan_input"],
                arguments=_decode_mapping(row["arguments_json"], "step arguments"),
                resolved_arguments=_decode_optional_mapping(
                    row["resolved_arguments_json"],
                    "resolved step arguments",
                ),
                classification=row["classification"],
                status=DurableStepStatus(row["status"]),
                operation_id=row["operation_id"],
                payload_hash=row["payload_hash"],
                attempt_count=row["attempt_count"],
                result=_decode_optional_mapping(row["result_json"], "step result"),
                error=_decode_optional_mapping(row["error_json"], "step error"),
                artifact=_decode_optional_mapping(row["artifact_json"], "step artifact"),
                metadata=_decode_mapping(row["metadata_json"], "step metadata"),
                created_at=_decode_time(row["created_at"], "step created_at"),
                updated_at=_decode_time(row["updated_at"], "step updated_at"),
            )
            for row in step_rows
        ]
        return ExecutionRun(
            execution_id=run_row["execution_id"],
            objective=run_row["objective"],
            conversation_id=run_row["conversation_id"],
            status=ExecutionRunStatus(run_row["status"]),
            plan_version=run_row["plan_version"],
            current_step_id=run_row["current_step_id"],
            next_step_id=run_row["next_step_id"],
            attempt_count=run_row["attempt_count"],
            iteration_count=run_row["iteration_count"],
            final_response=run_row["final_response"],
            execution_context=_decode_mapping(
                run_row["execution_context_json"],
                "execution context",
            ),
            variables=_decode_mapping(run_row["variables_json"], "variables"),
            metadata=_decode_mapping(run_row["metadata_json"], "metadata"),
            steps=steps,
            created_at=_decode_time(run_row["created_at"], "run created_at"),
            updated_at=_decode_time(run_row["updated_at"], "run updated_at"),
        )
    except (TypeError, ValueError) as exc:
        raise DurableStateCorruptionError("Durable aggregate is invalid") from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode_time(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _decode_time(value: str | None, field_name: str) -> datetime:
    if value is None:
        raise DurableStateCorruptionError(f"{field_name} is missing")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DurableStateCorruptionError(f"{field_name} is invalid") from exc
