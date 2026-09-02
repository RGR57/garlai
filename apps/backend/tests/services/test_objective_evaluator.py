from src.models.execution_state import ExecutionState, StepResult
from src.services.objective_evaluator import ObjectiveEvaluator


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
