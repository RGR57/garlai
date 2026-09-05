from pathlib import Path

import pytest

from src.models.durable_execution import (
    ApprovalRequest,
    DurableStep,
    DurableStepStatus,
    ExecutionRun,
    canonical_payload_hash,
)
from src.repositories.sqlite_durable_execution_repository import SQLiteDurableExecutionRepository
from src.services.durable_execution_service import DurableExecutionService
from src.services.objective_evaluator import ObjectiveEvaluator
from src.services.recovery_service import RecoveryService


OBJECTIVE = (
    "On this SaaS marketplace, find the cheapest plan that supports SSO and at least "
    "10 users, prepare the signup using supplied TEST details, and ask me before making "
    "the final commitment."
)


@pytest.mark.anyio
async def test_fresh_service_projects_durable_approval_operation_and_confirmation_facts(tmp_path: Path):
    database_path = tmp_path / "objective-evidence.sqlite3"
    repository = SQLiteDurableExecutionRepository(database_path)
    await repository.initialize()
    arguments = {
        "target": {"semantic": "Confirm Pro signup"},
        "expected_success_text": "Signup complete",
    }
    payload_hash = canonical_payload_hash("browser_submit", "Confirm Pro signup", arguments)
    await repository.create_planning_run(ExecutionRun(execution_id="web-run", objective=OBJECTIVE))
    await repository.persist_validated_plan(
        "web-run",
        [
            DurableStep(
                step_id=4,
                ordinal=0,
                action="Confirm Pro signup",
                tool="browser_submit",
                arguments=arguments,
                resolved_arguments=arguments,
                operation_id="submit-operation",
                payload_hash=payload_hash,
            )
        ],
    )
    approval = ApprovalRequest.create(
        approval_id="approval-1",
        execution_id="web-run",
        step_id=4,
        operation_id="submit-operation",
        tool="browser_submit",
        action="Confirm Pro signup",
        arguments=arguments,
        reason="Final commitment",
        risk_level="high",
    )
    await repository.request_approval(approval)
    await repository.approve("web-run", approval.approval_id, approval.payload_hash)
    claim = await repository.claim_operation("web-run", 4, "submit-operation", payload_hash)
    await repository.record_operation_outcome(
        claim,
        DurableStepStatus.COMPLETED,
        result={
            "output": {
                "receipt": {
                    "confirmation": {
                        "observation_id": "confirmation-observation",
                        "confirmation_hash": "persisted-confirmation-hash",
                    }
                }
            }
        },
    )

    fresh_service = DurableExecutionService(SQLiteDurableExecutionRepository(database_path))
    context = await fresh_service.objective_evaluation_context("web-run")
    state = (await RecoveryService(SQLiteDurableExecutionRepository(database_path)).prepare_resume("web-run")).execution_state

    assert [(fact.operation_id, fact.event_type) for fact in context.approvals] == [
        ("submit-operation", "requested"),
        ("submit-operation", "approved"),
    ]
    assert [(fact.operation_id, fact.event_type) for fact in context.operations] == [
        ("submit-operation", "intent_recorded"),
        ("submit-operation", "completed"),
    ]
    assert context.confirmations[0].operation_id == "submit-operation"
    assert context.confirmations[0].observation_id == "confirmation-observation"
    assert context.confirmations[0].confirmation_hash == "persisted-confirmation-hash"
    assert ObjectiveEvaluator().evaluate(OBJECTIVE, state, [], context).complete is False
