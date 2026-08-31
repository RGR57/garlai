from __future__ import annotations

from typing import Protocol

from src.models.durable_execution import DurableStep, ExecutionRun


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
