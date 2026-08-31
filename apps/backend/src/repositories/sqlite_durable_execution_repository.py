from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from src.models.durable_execution import (
    DurableStateCorruptionError,
    ApprovalEventType,
    ApprovalPayloadMismatchError,
    ApprovalRequest,
    DurableStep,
    DurableStepStatus,
    ExecutionRun,
    ExecutionRunStatus,
    OperationClaim,
    OperationEventType,
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

    async def claim_operation(
        self,
        execution_id: str,
        step_id: int,
        operation_id: str,
        payload_hash: str,
    ) -> OperationClaim:
        return await self._run(
            lambda: self._claim_operation(
                execution_id,
                step_id,
                operation_id,
                payload_hash,
            )
        )

    async def operation_events(
        self,
        operation_id: str,
    ) -> list[OperationEventType]:
        return await self._run(lambda: self._operation_events(operation_id))

    async def record_operation_outcome(
        self,
        claim: OperationClaim,
        status: DurableStepStatus,
        *,
        result: dict | None = None,
        error: dict | None = None,
        artifact: dict | None = None,
    ) -> None:
        await self._run(
            lambda: self._record_operation_outcome(
                claim,
                status,
                result=result,
                error=error,
                artifact=artifact,
            )
        )

    async def mark_operation_uncertain(
        self,
        execution_id: str,
        step_id: int,
        operation_id: str,
        reason: str,
    ) -> None:
        await self._run(
            lambda: self._mark_operation_uncertain(
                execution_id,
                step_id,
                operation_id,
                reason,
            )
        )

    async def claim_read_only_step(self, execution_id: str, step_id: int) -> bool:
        return await self._run(
            lambda: self._claim_read_only_step(execution_id, step_id)
        )

    async def record_read_only_outcome(
        self,
        execution_id: str,
        step_id: int,
        status: DurableStepStatus,
        *,
        result: dict | None = None,
        error: dict | None = None,
    ) -> None:
        await self._run(
            lambda: self._record_read_only_outcome(
                execution_id,
                step_id,
                status,
                result=result,
                error=error,
            )
        )

    async def request_approval(self, approval: ApprovalRequest) -> None:
        await self._run(lambda: self._request_approval(approval))

    async def get_approval(
        self, execution_id: str, approval_id: str
    ) -> ApprovalRequest:
        return await self._run(
            lambda: self._get_approval(execution_id, approval_id)
        )

    async def approve(
        self, execution_id: str, approval_id: str, payload_hash: str
    ) -> ApprovalRequest:
        return await self._run(
            lambda: self._approve(execution_id, approval_id, payload_hash)
        )

    async def reject(self, execution_id: str, approval_id: str) -> None:
        await self._run(lambda: self._reject(execution_id, approval_id))

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

    def _claim_operation(
        self,
        execution_id: str,
        step_id: int,
        operation_id: str,
        payload_hash: str,
    ) -> OperationClaim:
        attempt_id = str(uuid.uuid4())
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE execution_steps
                SET status = ?, attempt_count = attempt_count + 1, updated_at = ?
                WHERE execution_id = ? AND step_id = ? AND status = ?
                  AND operation_id = ? AND payload_hash = ?
                """,
                (
                    DurableStepStatus.EXECUTING.value,
                    _now(),
                    execution_id,
                    step_id,
                    DurableStepStatus.PENDING.value,
                    operation_id,
                    payload_hash,
                ),
            ).rowcount
            if updated != 1:
                connection.rollback()
                return OperationClaim.denied(execution_id, step_id, operation_id)
            connection.execute(
                """
                INSERT INTO operation_journal (
                    operation_event_id, execution_id, step_id, operation_id,
                    event_type, attempt_id, payload_hash, fact_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    execution_id,
                    step_id,
                    operation_id,
                    OperationEventType.INTENT_RECORDED.value,
                    attempt_id,
                    payload_hash,
                    _encode_json({}),
                    _now(),
                ),
            )
            connection.commit()
            return OperationClaim(
                True,
                execution_id,
                step_id,
                operation_id,
                attempt_id,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _operation_events(self, operation_id: str) -> list[OperationEventType]:
        connection = self._connect()
        try:
            return [
                OperationEventType(row["event_type"])
                for row in connection.execute(
                    """
                    SELECT event_type FROM operation_journal
                    WHERE operation_id = ? ORDER BY occurred_at
                    """,
                    (operation_id,),
                )
            ]
        finally:
            connection.close()

    def _record_operation_outcome(
        self,
        claim: OperationClaim,
        status: DurableStepStatus,
        *,
        result: dict | None,
        error: dict | None,
        artifact: dict | None,
    ) -> None:
        if not claim.granted:
            raise ValueError("Only a granted operation claim may record an outcome.")
        if status not in {
            DurableStepStatus.COMPLETED,
            DurableStepStatus.KNOWN_FAILED,
        }:
            raise ValueError("Operation outcomes must be confirmed terminal facts.")

        event_type = OperationEventType(status.value)
        fact = {"result": result, "error": error, "artifact": artifact}
        encoded_fact = _encode_json(fact)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, operation_id, payload_hash, result_json, error_json,
                       artifact_json
                FROM execution_steps
                WHERE execution_id = ? AND step_id = ?
                """,
                (claim.execution_id, claim.step_id),
            ).fetchone()
            if row is None or row["operation_id"] != claim.operation_id:
                raise ValueError("Operation claim does not match a durable step.")
            if row["status"] == status.value:
                existing = connection.execute(
                    """
                    SELECT fact_json FROM operation_journal
                    WHERE operation_id = ? AND event_type = ?
                    """,
                    (claim.operation_id, event_type.value),
                ).fetchone()
                aggregate_matches = (
                    row["result_json"] == _encode_optional_mapping(result, "operation result")
                    and row["error_json"] == _encode_optional_mapping(error, "operation error")
                    and row["artifact_json"] == _encode_optional_mapping(artifact, "operation artifact")
                )
                if (
                    existing is not None
                    and existing["fact_json"] == encoded_fact
                    and aggregate_matches
                ):
                    connection.commit()
                    return
                raise ValueError("Conflicting terminal operation outcome.")
            if row["status"] != DurableStepStatus.EXECUTING.value:
                raise ValueError("Operation is not awaiting a terminal outcome.")
            has_intent = connection.execute(
                """
                SELECT 1 FROM operation_journal
                WHERE operation_id = ? AND event_type = ? AND attempt_id = ?
                """,
                (
                    claim.operation_id,
                    OperationEventType.INTENT_RECORDED.value,
                    claim.attempt_id,
                ),
            ).fetchone()
            if has_intent is None:
                raise ValueError("Operation outcome has no matching committed intent.")
            connection.execute(
                """
                UPDATE execution_steps
                SET status = ?, result_json = ?, error_json = ?, artifact_json = ?,
                    updated_at = ?
                WHERE execution_id = ? AND step_id = ? AND status = ?
                """,
                (
                    status.value,
                    _encode_optional_mapping(result, "operation result"),
                    _encode_optional_mapping(error, "operation error"),
                    _encode_optional_mapping(artifact, "operation artifact"),
                    _now(),
                    claim.execution_id,
                    claim.step_id,
                    DurableStepStatus.EXECUTING.value,
                ),
            )
            connection.execute(
                """
                INSERT INTO operation_journal (
                    operation_event_id, execution_id, step_id, operation_id,
                    event_type, attempt_id, payload_hash, fact_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    claim.execution_id,
                    claim.step_id,
                    claim.operation_id,
                    event_type.value,
                    claim.attempt_id,
                    row["payload_hash"],
                    encoded_fact,
                    _now(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _mark_operation_uncertain(
        self,
        execution_id: str,
        step_id: int,
        operation_id: str,
        reason: str,
    ) -> None:
        encoded_fact = _encode_json({"reason": reason})
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, payload_hash FROM execution_steps
                WHERE execution_id = ? AND step_id = ? AND operation_id = ?
                """,
                (execution_id, step_id, operation_id),
            ).fetchone()
            if row is None:
                raise ValueError("Unknown durable operation.")
            if row["status"] == DurableStepStatus.UNCERTAIN.value:
                existing = connection.execute(
                    """
                    SELECT fact_json FROM operation_journal
                    WHERE operation_id = ? AND event_type = ?
                    """,
                    (operation_id, OperationEventType.UNCERTAIN.value),
                ).fetchone()
                if existing is not None and existing["fact_json"] == encoded_fact:
                    connection.commit()
                    return
                raise ValueError("Conflicting uncertainty fact.")
            if row["status"] != DurableStepStatus.EXECUTING.value:
                raise ValueError("Only an executing operation may become uncertain.")
            intent = connection.execute(
                """
                SELECT attempt_id FROM operation_journal
                WHERE operation_id = ? AND event_type = ?
                """,
                (operation_id, OperationEventType.INTENT_RECORDED.value),
            ).fetchone()
            if intent is None:
                raise ValueError("Uncertainty requires a committed operation intent.")
            connection.execute(
                """
                UPDATE execution_steps SET status = ?, error_json = ?, updated_at = ?
                WHERE execution_id = ? AND step_id = ? AND status = ?
                """,
                (
                    DurableStepStatus.UNCERTAIN.value,
                    _encode_json({"reason": reason}),
                    _now(),
                    execution_id,
                    step_id,
                    DurableStepStatus.EXECUTING.value,
                ),
            )
            run_updated = connection.execute(
                """
                UPDATE execution_runs SET status = ?, updated_at = ?
                WHERE execution_id = ? AND status = ?
                """,
                (
                    ExecutionRunStatus.RECOVERY_REQUIRED.value,
                    _now(),
                    execution_id,
                    ExecutionRunStatus.RUNNING.value,
                ),
            ).rowcount
            if run_updated != 1:
                raise ValueError("Uncertainty requires a running durable execution.")
            connection.execute(
                """
                INSERT INTO operation_journal (
                    operation_event_id, execution_id, step_id, operation_id,
                    event_type, attempt_id, payload_hash, fact_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    execution_id,
                    step_id,
                    operation_id,
                    OperationEventType.UNCERTAIN.value,
                    intent["attempt_id"],
                    row["payload_hash"],
                    encoded_fact,
                    _now(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _claim_read_only_step(self, execution_id: str, step_id: int) -> bool:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE execution_steps
                SET status = ?, attempt_count = attempt_count + 1, updated_at = ?
                WHERE execution_id = ? AND step_id = ? AND status = ?
                  AND operation_id IS NULL
                """,
                (
                    DurableStepStatus.EXECUTING.value,
                    _now(),
                    execution_id,
                    step_id,
                    DurableStepStatus.PENDING.value,
                ),
            ).rowcount
            connection.commit()
            return updated == 1
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _record_read_only_outcome(
        self,
        execution_id: str,
        step_id: int,
        status: DurableStepStatus,
        *,
        result: dict | None,
        error: dict | None,
    ) -> None:
        if status not in {
            DurableStepStatus.COMPLETED,
            DurableStepStatus.KNOWN_FAILED,
        }:
            raise ValueError("Read-only steps require a confirmed outcome.")
        connection = self._connect()
        try:
            updated = connection.execute(
                """
                UPDATE execution_steps
                SET status = ?, result_json = ?, error_json = ?, updated_at = ?
                WHERE execution_id = ? AND step_id = ? AND status = ?
                  AND operation_id IS NULL
                """,
                (
                    status.value,
                    _encode_optional_mapping(result, "read-only result"),
                    _encode_optional_mapping(error, "read-only error"),
                    _now(),
                    execution_id,
                    step_id,
                    DurableStepStatus.EXECUTING.value,
                ),
            ).rowcount
            if updated != 1:
                raise ValueError("Read-only step is not awaiting an outcome.")
        finally:
            connection.close()

    def _request_approval(self, approval: ApprovalRequest) -> None:
        payload = _approval_payload(approval)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE execution_steps SET status = ?, updated_at = ?
                WHERE execution_id = ? AND step_id = ? AND status = ?
                  AND operation_id = ? AND payload_hash = ?
                """,
                (
                    DurableStepStatus.WAITING_APPROVAL.value,
                    _now(),
                    approval.execution_id,
                    approval.step_id,
                    DurableStepStatus.PENDING.value,
                    approval.operation_id,
                    approval.payload_hash,
                ),
            ).rowcount
            if updated != 1:
                raise ValueError("Approval request does not match a pending operation.")
            connection.execute(
                """
                INSERT INTO approval_journal (
                    approval_event_id, approval_id, execution_id, step_id,
                    operation_id, event_type, canonical_payload_json, payload_hash,
                    occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()), approval.approval_id, approval.execution_id,
                    approval.step_id, approval.operation_id,
                    ApprovalEventType.REQUESTED.value, _encode_json(payload),
                    approval.payload_hash, _now(),
                ),
            )
            run_updated = connection.execute(
                """
                UPDATE execution_runs SET status = ?, updated_at = ?
                WHERE execution_id = ? AND status = ?
                """,
                (
                    ExecutionRunStatus.WAITING_APPROVAL.value, _now(),
                    approval.execution_id, ExecutionRunStatus.RUNNING.value,
                ),
            ).rowcount
            if run_updated != 1:
                raise ValueError("Approval request requires a running execution.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _get_approval(self, execution_id: str, approval_id: str) -> ApprovalRequest:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM approval_journal WHERE execution_id = ? AND approval_id = ?
                ORDER BY occurred_at, rowid
                """, (execution_id, approval_id)
            ).fetchall()
            if not rows:
                raise KeyError("Unknown approval for this execution.")
            requested = next(
                (row for row in rows if row["event_type"] == ApprovalEventType.REQUESTED.value),
                None,
            )
            if requested is None:
                raise DurableStateCorruptionError("Approval is missing its request fact.")
            payload = _decode_mapping(requested["canonical_payload_json"], "approval payload")
            return ApprovalRequest(
                approval_id=approval_id, execution_id=execution_id,
                step_id=requested["step_id"], operation_id=requested["operation_id"],
                tool=payload["tool"], action=payload["action"],
                arguments=payload["arguments"], reason=payload["reason"],
                risk_level=payload["risk_level"], payload_hash=requested["payload_hash"],
                event_type=ApprovalEventType(rows[-1]["event_type"]),
                requested_at=_decode_time(requested["occurred_at"], "approval occurred_at"),
            )
        finally:
            connection.close()

    def _approve(
        self, execution_id: str, approval_id: str, payload_hash: str
    ) -> ApprovalRequest:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            approval = self._get_approval_in_transaction(connection, execution_id, approval_id)
            approval.assert_authorizes(execution_id=execution_id, payload_hash=payload_hash)
            if approval.event_type is not ApprovalEventType.REQUESTED:
                raise ValueError("Approval is no longer pending.")
            updated = connection.execute(
                """
                UPDATE execution_steps SET status = ?, updated_at = ?
                WHERE execution_id = ? AND step_id = ? AND status = ?
                  AND operation_id = ? AND payload_hash = ?
                """, (
                    DurableStepStatus.PENDING.value, _now(), execution_id,
                    approval.step_id, DurableStepStatus.WAITING_APPROVAL.value,
                    approval.operation_id, approval.payload_hash,
                )
            ).rowcount
            if updated != 1:
                raise ValueError("Approved operation no longer matches its frozen step.")
            connection.execute(
                """
                INSERT INTO approval_journal (
                    approval_event_id, approval_id, execution_id, step_id,
                    operation_id, event_type, canonical_payload_json, payload_hash,
                    occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()), approval_id, execution_id, approval.step_id,
                    approval.operation_id, ApprovalEventType.APPROVED.value,
                    _encode_json(_approval_payload(approval)), approval.payload_hash, _now(),
                )
            )
            connection.execute(
                "UPDATE execution_runs SET status = ?, updated_at = ? WHERE execution_id = ? AND status = ?",
                (ExecutionRunStatus.RUNNING.value, _now(), execution_id, ExecutionRunStatus.WAITING_APPROVAL.value),
            )
            connection.commit()
            return ApprovalRequest(**{**approval.__dict__, "event_type": ApprovalEventType.APPROVED})
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _reject(self, execution_id: str, approval_id: str) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            approval = self._get_approval_in_transaction(connection, execution_id, approval_id)
            if approval.event_type is not ApprovalEventType.REQUESTED:
                raise ValueError("Approval is no longer pending.")
            updated = connection.execute(
                "UPDATE execution_steps SET status = ?, updated_at = ? WHERE execution_id = ? AND step_id = ? AND status = ?",
                (DurableStepStatus.REJECTED.value, _now(), execution_id, approval.step_id, DurableStepStatus.WAITING_APPROVAL.value),
            ).rowcount
            if updated != 1:
                raise ValueError("Rejected operation no longer matches its frozen step.")
            connection.execute(
                """
                INSERT INTO approval_journal (approval_event_id, approval_id, execution_id, step_id, operation_id, event_type, canonical_payload_json, payload_hash, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), approval_id, execution_id, approval.step_id, approval.operation_id, ApprovalEventType.REJECTED.value, _encode_json(_approval_payload(approval)), approval.payload_hash, _now())
            )
            connection.execute(
                "UPDATE execution_runs SET status = ?, updated_at = ? WHERE execution_id = ? AND status = ?",
                (ExecutionRunStatus.FAILED.value, _now(), execution_id, ExecutionRunStatus.WAITING_APPROVAL.value),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _get_approval_in_transaction(self, connection, execution_id, approval_id):
        rows = connection.execute(
            "SELECT * FROM approval_journal WHERE execution_id = ? AND approval_id = ? ORDER BY occurred_at, rowid",
            (execution_id, approval_id),
        ).fetchall()
        if not rows:
            raise KeyError("Unknown approval for this execution.")
        requested = next((row for row in rows if row["event_type"] == ApprovalEventType.REQUESTED.value), None)
        if requested is None:
            raise DurableStateCorruptionError("Approval is missing its request fact.")
        payload = _decode_mapping(requested["canonical_payload_json"], "approval payload")
        return ApprovalRequest(
            approval_id=approval_id, execution_id=execution_id, step_id=requested["step_id"], operation_id=requested["operation_id"],
            tool=payload["tool"], action=payload["action"], arguments=payload["arguments"], reason=payload["reason"],
            risk_level=payload["risk_level"], payload_hash=requested["payload_hash"],
            event_type=ApprovalEventType(rows[-1]["event_type"]), requested_at=_decode_time(requested["occurred_at"], "approval occurred_at"),
        )


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


def _approval_payload(approval: ApprovalRequest) -> dict:
    return {
        "tool": approval.tool,
        "action": approval.action,
        "arguments": approval.arguments,
        "reason": approval.reason,
        "risk_level": approval.risk_level,
    }


def _encode_optional_json(value: object | None) -> str | None:
    return None if value is None else _encode_json(value)


def _encode_optional_mapping(
    value: dict | None,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return _encode_json(value)


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
