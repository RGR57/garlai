from __future__ import annotations

import uuid

from src.models.durable_execution import (
    DurableStep,
    ExecutionRun,
    canonical_payload_hash,
)
from src.models.plan import ExecutionPlan
from src.repositories.durable_execution_repository import DurableExecutionRepository
from src.services.execution_reconciler import ExecutionReconciler
from src.services.objective_evaluator import (
    ExternalConfirmationEvidence,
    ObjectiveEvaluationContext,
)
from src.services.recovery_service import RecoveryDecision, RecoveryService


class DurableExecutionService:
    """Own creation and one-time materialization of durable execution runs."""

    def __init__(
        self,
        repository: DurableExecutionRepository,
        reconciler: ExecutionReconciler | None = None,
    ) -> None:
        self.repository = repository
        self.recovery_service = RecoveryService(repository, reconciler=reconciler)

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

    async def objective_evaluation_context(
        self,
        execution_id: str,
    ) -> ObjectiveEvaluationContext:
        """Project only bounded, authoritative durable facts for evaluation."""
        run = await self.repository.load(execution_id)
        confirmations: list[ExternalConfirmationEvidence] = []
        for step in run.steps:
            if step.operation_id is None or step.payload_hash is None or not step.result:
                continue
            output = step.result.get("output")
            receipt = output.get("receipt") if isinstance(output, dict) else None
            confirmation = receipt.get("confirmation") if isinstance(receipt, dict) else None
            if not isinstance(confirmation, dict):
                continue
            observation_id = confirmation.get("observation_id")
            confirmation_hash = confirmation.get("confirmation_hash")
            if not isinstance(observation_id, str) or not isinstance(confirmation_hash, str):
                continue
            confirmations.append(
                ExternalConfirmationEvidence(
                    execution_id=run.execution_id,
                    step_id=step.step_id,
                    operation_id=step.operation_id,
                    payload_hash=step.payload_hash,
                    observation_id=observation_id,
                    confirmation_hash=confirmation_hash,
                )
            )
        return ObjectiveEvaluationContext(
            approvals=tuple(await self.repository.list_approval_evidence(execution_id)),
            operations=tuple(await self.repository.list_operation_evidence(execution_id)),
            confirmations=tuple(confirmations),
        )

    async def complete_if_finished(self, execution_id: str) -> bool:
        return await self.repository.complete_if_finished(execution_id)

    async def fail_if_finished(self, execution_id: str) -> bool:
        return await self.repository.fail_if_finished(execution_id)

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
            result_contract=step.result_contract,
            arguments=step.arguments,
            operation_id=operation_id,
            payload_hash=payload_hash,
        )
