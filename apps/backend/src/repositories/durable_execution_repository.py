from __future__ import annotations

from typing import Protocol

from src.models.durable_execution import (
    ApprovalRequest,
    DurableStep,
    DurableStepStatus,
    ExecutionRun,
    OperationClaim,
    OrphanedOperation,
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

    async def patch_execution_context(
        self,
        execution_id: str,
        patch: dict,
    ) -> ExecutionRun:
        """Deep-merge constrained execution-scoped facts for a nonterminal run."""

    async def list_recoverable(self) -> list[ExecutionRun]:
        """List runs that may be inspected by an explicit recovery request."""

    async def record_reconciliation(
        self,
        execution_id: str,
        execution_context_patch: dict,
        recovery_reason: str | None = None,
    ) -> None:
        """Atomically persist recovery observations and an optional stop reason."""

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
        execution_context_patch: dict | None = None,
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

    async def list_orphaned_operations(
        self, execution_id: str
    ) -> list[OrphanedOperation]:
        """List committed intents that have no durable terminal outcome."""

    async def recover_orphaned_operation_claim(
        self,
        execution_id: str,
        step_id: int,
        operation_id: str,
    ) -> OperationClaim:
        """Reconstruct the committed intent identity for a proven recovery outcome."""

    async def prepare_tool_step(
        self,
        execution_id: str,
        step_id: int,
        resolved_arguments: dict,
    ) -> DurableStep:
        """Freeze one pending tool payload before it can be authorized or invoked."""

    async def claim_read_only_step(self, execution_id: str, step_id: int) -> bool:
        """Conditionally begin a retry-safe read-only step."""

    async def record_read_only_outcome(
        self,
        execution_id: str,
        step_id: int,
        status: DurableStepStatus,
        *,
        result: dict | None = None,
        error: dict | None = None,
        execution_context_patch: dict | None = None,
    ) -> None:
        """Persist the confirmed outcome of a claimed read-only step."""

    async def complete_if_finished(self, execution_id: str) -> bool:
        """Mark a running execution complete only after every step succeeds."""

    async def fail_if_finished(self, execution_id: str) -> bool:
        """Mark exhausted work failed when its objective criteria are unmet."""

    async def request_approval(self, approval: ApprovalRequest) -> None:
        """Persist an immutable approval request for one exact operation."""

    async def get_approval(
        self, execution_id: str, approval_id: str
    ) -> ApprovalRequest:
        """Load an immutable approval by authoritative execution identity."""

    async def get_pending_approval(
        self, execution_id: str
    ) -> ApprovalRequest | None:
        """Load the sole frozen approval that keeps this run paused, if any."""

    async def approve(
        self, execution_id: str, approval_id: str, payload_hash: str
    ) -> ApprovalRequest:
        """Approve exactly one frozen payload and make its step claimable."""

    async def reject(self, execution_id: str, approval_id: str) -> None:
        """Reject one frozen approval without invoking its operation."""

    async def invalidate_approval(
        self,
        execution_id: str,
        approval_id: str,
        reason: str,
    ) -> None:
        """Preserve an approved-but-stale operation as a recovery requirement."""
