from __future__ import annotations

from dataclasses import dataclass

from src.models.durable_execution import (
    ApprovalRequest,
    DurableStepStatus,
    ExecutionRun,
    ExecutionRunStatus,
)
from src.models.execution_state import ExecutionState, StepResult
from src.repositories.durable_execution_repository import DurableExecutionRepository


ORPHANED_OPERATION_REASON = (
    "Recovery found a committed operation intent without a confirmed outcome."
)


@dataclass(frozen=True)
class RecoveryDecision:
    run: ExecutionRun
    status: ExecutionRunStatus
    may_execute: bool
    next_step_id: int | None
    execution_state: ExecutionState
    pending_approval: ApprovalRequest | None = None
    planning_required: bool = False


class RecoveryService:
    """Rebuild a runtime view without recreating or invoking persisted work."""

    def __init__(self, repository: DurableExecutionRepository) -> None:
        self.repository = repository

    async def prepare_resume(self, execution_id: str) -> RecoveryDecision:
        run = await self.repository.load(execution_id)

        if run.status is ExecutionRunStatus.PLANNING:
            return self._decision(run, planning_required=True)

        if run.status.is_terminal:
            return self._decision(run)

        if run.status is ExecutionRunStatus.WAITING_APPROVAL:
            approval = await self.repository.get_pending_approval(execution_id)
            if approval is None:
                raise ValueError("Waiting execution has no pending approval.")
            return self._decision(run, pending_approval=approval)

        if run.status is ExecutionRunStatus.RUNNING:
            for orphan in await self.repository.list_orphaned_operations(execution_id):
                try:
                    await self.repository.mark_operation_uncertain(
                        orphan.execution_id,
                        orphan.step_id,
                        orphan.operation_id,
                        ORPHANED_OPERATION_REASON,
                    )
                except ValueError:
                    latest = await self.repository.load(execution_id)
                    step = next(
                        (
                            candidate
                            for candidate in latest.steps
                            if candidate.step_id == orphan.step_id
                        ),
                        None,
                    )
                    if step is None or step.status not in {
                        DurableStepStatus.COMPLETED,
                        DurableStepStatus.KNOWN_FAILED,
                    }:
                        raise
            run = await self.repository.load(execution_id)

        if run.status is ExecutionRunStatus.RECOVERY_REQUIRED:
            return self._decision(run)

        next_step_id = self._first_pending_step_id(run)
        return self._decision(run, may_execute=next_step_id is not None, next_step_id=next_step_id)

    def _decision(
        self,
        run: ExecutionRun,
        *,
        may_execute: bool = False,
        next_step_id: int | None = None,
        pending_approval: ApprovalRequest | None = None,
        planning_required: bool = False,
    ) -> RecoveryDecision:
        state = self._rebuild_execution_state(run, next_step_id, pending_approval)
        return RecoveryDecision(
            run=run,
            status=run.status,
            may_execute=may_execute,
            next_step_id=next_step_id,
            execution_state=state,
            pending_approval=pending_approval,
            planning_required=planning_required,
        )

    @staticmethod
    def _first_pending_step_id(run: ExecutionRun) -> int | None:
        for step in run.steps:
            if step.status is DurableStepStatus.PENDING:
                return step.step_id
        return None

    @staticmethod
    def _rebuild_execution_state(
        run: ExecutionRun,
        next_step_id: int | None,
        pending_approval: ApprovalRequest | None,
    ) -> ExecutionState:
        state = ExecutionState(
            current_step=next_step_id or 0,
            attempt=run.attempt_count,
            variables=dict(run.variables),
        )
        for step in run.steps:
            if step.status is not DurableStepStatus.COMPLETED:
                continue
            output = step.result.get("output") if step.result else None
            state.variables.setdefault(f"step{step.step_id}", output)
            state.record(
                StepResult(
                    step_id=step.step_id,
                    success=True,
                    output=output,
                    tool=step.tool,
                    action=step.action,
                    metadata={"artifact": step.artifact} if step.artifact else {},
                )
            )
        if pending_approval is not None:
            state.require_approval(
                step_id=pending_approval.step_id,
                tool_name=pending_approval.tool,
                arguments=pending_approval.arguments,
                reason=pending_approval.reason,
                risk_level=pending_approval.risk_level,
            )
        return state
