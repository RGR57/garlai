from __future__ import annotations

import uuid

from src.models.durable_execution import (
    DurableStep,
    ExecutionRun,
    canonical_payload_hash,
)
from src.models.plan import ExecutionPlan
from src.repositories.durable_execution_repository import DurableExecutionRepository
from src.services.recovery_service import RecoveryDecision, RecoveryService


class DurableExecutionService:
    """Own creation and one-time materialization of durable execution runs."""

    def __init__(self, repository: DurableExecutionRepository) -> None:
        self.repository = repository
        self.recovery_service = RecoveryService(repository)

    async def start(
        self,
        *,
        objective: str,
        execution_context: dict,
        conversation_id: str | None = None,
        execution_id: str | None = None,
    ) -> ExecutionRun:
        run = ExecutionRun(
            execution_id=execution_id or str(uuid.uuid4()),
            objective=objective,
            conversation_id=conversation_id,
            execution_context=execution_context,
        )
        await self.repository.create_planning_run(run)
        return run

    async def persist_validated_plan(
        self,
        execution_id: str,
        plan: ExecutionPlan,
    ) -> ExecutionRun:
        if not isinstance(plan, ExecutionPlan) or not plan.steps:
            raise ValueError("A validated durable plan must contain at least one step.")

        steps = [
            self._to_durable_step(step, ordinal)
            for ordinal, step in enumerate(plan.steps)
        ]
        await self.repository.persist_validated_plan(execution_id, steps)
        return await self.repository.load(execution_id)

    async def prepare_resume(self, execution_id: str) -> RecoveryDecision:
        return await self.recovery_service.prepare_resume(execution_id)

    @staticmethod
    def _to_durable_step(step, ordinal: int) -> DurableStep:
        operation_id = str(uuid.uuid4()) if step.tool is not None else None
        payload_hash = (
            canonical_payload_hash(step.tool, step.action, step.arguments)
            if step.tool is not None
            else None
        )
        return DurableStep(
            step_id=step.id,
            ordinal=ordinal,
            action=step.action,
            tool=step.tool,
            plan_input=step.input,
            arguments=step.arguments,
            operation_id=operation_id,
            payload_hash=payload_hash,
        )
