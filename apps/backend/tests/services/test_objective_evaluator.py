from src.models.execution_state import ExecutionState, StepResult
import pytest

from src.services.objective_evaluator import (
    ApprovalEvidence,
    ExternalConfirmationEvidence,
    ObjectiveEvaluationContext,
    ObjectiveEvaluator,
    OperationEvidence,
)


def test_market_prototype_goal_requires_evidence_artifact_and_verification():
    state = ExecutionState()
    state.record(StepResult(step_id=1, success=True, tool="web_search", output={"evidence": []}))

    evaluation = ObjectiveEvaluator().evaluate(
        "Research a market and create and verify a working local prototype.",
        state,
        artifacts=[],
    )

    assert evaluation.complete is False
    assert evaluation.gaps == (
        "No valid research evidence was observed.",
        "No prototype artifact was observed.",
        "No successful verification was observed.",
    )


def test_evaluator_rejects_failed_verification_even_when_steps_completed():
    state = ExecutionState()
    state.record(StepResult(step_id=1, success=True, tool="web_search", output={"evidence": [{"url": "https://example.test"}]}))
    state.record(StepResult(step_id=2, success=True, tool="filesystem", output="prototype written"))
    state.record(StepResult(step_id=3, success=False, tool="terminal", error="tests failed"))

    evaluation = ObjectiveEvaluator().evaluate(
        "Research a market and create and verify a working local prototype.", state, artifacts=[]
    )

    assert evaluation.complete is False
    assert "Verification failed: tests failed" in evaluation.gaps


def test_evaluator_accepts_observed_research_prototype_and_verification():
    state = ExecutionState()
    state.record(StepResult(step_id=1, success=True, tool="web_search", output={"evidence": [{"url": "https://example.test"}]}))
    state.record(StepResult(step_id=2, success=True, tool="filesystem", output="prototype written"))
    state.record(StepResult(step_id=3, success=True, tool="terminal", output="tests passed"))

    evaluation = ObjectiveEvaluator().evaluate(
        "Research a market and create and verify a working local prototype.", state, artifacts=[]
    )

    assert evaluation.complete is True
    assert evaluation.gaps == ()
    assert evaluation.evidence == ({"url": "https://example.test"},)
    assert evaluation.verification == ("tests passed",)


WEB_OBJECTIVE = (
    "On this SaaS marketplace, find the cheapest plan that supports SSO and at least "
    "10 users, prepare the signup using supplied TEST details, and ask me before making "
    "the final commitment."
)


def _browser_state() -> ExecutionState:
    state = ExecutionState()
    observation = {
        "trust": "untrusted_external_page_data",
        "observation": {
            "observation_id": "pricing-observation",
            "elements": [
                {
                    "element_ref": "pricing-observation:pro",
                    "accessible_name": "Choose Pro",
                    "semantic_fingerprint": "pro-fingerprint",
                    "text_context": "Pro\n$40/month\nSSO: Yes\nUsers: 12",
                },
                {
                    "element_ref": "pricing-observation:business",
                    "accessible_name": "Choose Business",
                    "semantic_fingerprint": "business-fingerprint",
                    "text_context": "Business\n$80/month\nSSO: Yes\nUsers: 50",
                },
            ],
        },
    }
    target = {
        "observation_id": "pricing-observation",
        "element_ref": "pricing-observation:pro",
        "accessible_name": "Choose Pro",
        "semantic_fingerprint": "pro-fingerprint",
        "text_context": "Pro\n$40/month\nSSO: Yes\nUsers: 12",
    }
    state.record(StepResult(step_id=1, success=True, tool="browser_observe", output=observation))
    state.record(
        StepResult(
            step_id=2,
            success=True,
            tool="browser_select",
            output={"receipt": {"action": "select", "target": target}},
        )
    )
    state.record(
        StepResult(
            step_id=3,
            success=True,
            tool="browser_fill",
            output={"receipt": {"action": "fill", "target": {"accessible_name": "Name"}}},
        )
    )
    return state


def _evidence(
    *,
    approval: str | None = "approved",
    operation: str | None = "completed",
    confirmation: bool = True,
) -> ObjectiveEvaluationContext:
    approvals = () if approval is None else (
        ApprovalEvidence(
            execution_id="web-run",
            step_id=4,
            operation_id="submit-operation",
            payload_hash="frozen-submit-payload",
            event_type=approval,
        ),
    )
    operations = () if operation is None else (
        OperationEvidence(
            execution_id="web-run",
            step_id=4,
            operation_id="submit-operation",
            payload_hash="frozen-submit-payload",
            event_type=operation,
        ),
    )
    confirmations = () if not confirmation else (
        ExternalConfirmationEvidence(
            execution_id="web-run",
            step_id=4,
            operation_id="submit-operation",
            payload_hash="frozen-submit-payload",
            observation_id="confirmation-observation",
            confirmation_hash="confirmation-hash",
        ),
    )
    return ObjectiveEvaluationContext(
        approvals=approvals,
        operations=operations,
        confirmations=confirmations,
    )


@pytest.mark.parametrize(
    ("evidence", "expected_gap"),
    [
        (_evidence(approval=None), "No durable approval granted for the final commitment."),
        (_evidence(approval="rejected"), "The final commitment approval was rejected."),
        (_evidence(operation=None), "No completed durable final commitment operation was observed."),
        (_evidence(confirmation=False), "No persisted external success confirmation was observed."),
    ],
)
def test_web_objective_requires_each_authoritative_commitment_fact(evidence, expected_gap):
    evaluation = ObjectiveEvaluator().evaluate(WEB_OBJECTIVE, _browser_state(), [], evidence)

    assert evaluation.complete is False
    assert expected_gap in evaluation.gaps


def test_web_objective_accepts_linked_durable_approval_operation_and_confirmation():
    evaluation = ObjectiveEvaluator().evaluate(WEB_OBJECTIVE, _browser_state(), [], _evidence())

    assert evaluation.complete is True
    assert evaluation.gaps == ()
