from __future__ import annotations

from typing import Protocol

from src.models.durable_execution import (
    DurableStep,
    DurableStepStatus,
    ExecutionRun,
    OperationClaim,
)


class DurableExecutionRepository(Protocol):
    """Durable execution aggregate boundary for GARL runtime services."""

    async def initialize(self) -> None:
        """Apply durable execution storage migrations."""

    async def create_planning_run(self, run: ExecutionRun) -> None:
        """Persist a durable run before a validated plan exists."""

    async def persist_validated_plan(
        self,
        execution_id: str,
        steps: list[DurableStep],
    ) -> None:
        """Persist one validated plan and transition its run to running."""

    async def load(self, execution_id: str) -> ExecutionRun:
        """Load and validate one durable execution aggregate."""

    async def list_recoverable(self) -> list[ExecutionRun]:
        """List runs that may be inspected by an explicit recovery request."""

    async def delete_for_test(self, execution_id: str) -> None:
        """Remove one execution only for deterministic test cleanup."""

    async def claim_operation(
        self,
        execution_id: str,
        step_id: int,
        operation_id: str,
        payload_hash: str,
    ) -> OperationClaim:
        """Atomically claim a consequential operation before invocation."""

    async def record_operation_outcome(
        self,
        claim: OperationClaim,
        status: DurableStepStatus,
        *,
        result: dict | None = None,
        error: dict | None = None,
        artifact: dict | None = None,
    ) -> None:
        """Persist one proven terminal outcome for an already claimed operation."""

    async def mark_operation_uncertain(
        self,
        execution_id: str,
        step_id: int,
        operation_id: str,
        reason: str,
    ) -> None:
        """Stop recovery when a claimed consequential invocation is ambiguous."""
