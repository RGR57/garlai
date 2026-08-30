import unittest

from src.models.chat_response import ChatResponse
from src.models.cognitive_state import CognitiveState
from src.models.conversation import ConversationMessage
from src.models.decision import Decision, DecisionType
from src.models.execution_state import StepResult
from src.models.plan import ExecutionPlan, PlanStep
from src.models.reasoning import ReasoningChain
from src.services.cognitive_pipeline import CognitivePipeline
from src.services.plan_scorer import PlanScore
from src.services.plan_validator import ValidationResult


class FakeReasoning:

    async def analyze(
        self,
        state: CognitiveState,
    ) -> ReasoningChain:
        return ReasoningChain()


class FakeCandidatePlanGenerator:

    async def generate(
        self,
        messages,
        state,
        candidates=1,
    ):
        return [
            ExecutionPlan(
                steps=[
                    PlanStep(
                        id=1,
                        action="Try transient work",
                        tool=None,
                        input="try",
                    )
                ]
            )
        ]


class FakePlanValidator:

    def validate(
        self,
        plan,
        state,
    ) -> ValidationResult:
        return ValidationResult(
            valid=True,
            score=100.0,
        )


class FakePlanScorer:

    def score(
        self,
        plan,
        state,
    ) -> PlanScore:
        return PlanScore(
            score=100.0,
        )


class AlwaysFailingExecutor:

    def __init__(
        self,
    ):
        self.calls = 0

    async def execute(
        self,
        messages,
        plan,
        state,
    ):
        self.calls += 1
        state.record(
            StepResult(
                step_id=1,
                success=False,
                error="timeout while calling tool",
            )
        )
        return "timeout while calling tool"


class FakeReviewer:

    async def review(
        self,
        state,
    ):
        return False, "timeout while calling tool"


class AlwaysRetryDecision:

    async def decide(
        self,
        state,
    ) -> Decision:
        return Decision(
            action=DecisionType.RETRY,
            reason="transient failure",
        )


class FakeResponseComposer:

    async def compose(
        self,
        execution_state,
    ) -> ChatResponse:
        return ChatResponse(
            response="unexpected success",
        )


class CognitivePipelineTests(
    unittest.IsolatedAsyncioTestCase
):

    async def test_retry_exhaustion_returns_last_failure_without_crashing(
        self,
    ):
        executor = AlwaysFailingExecutor()
        pipeline = CognitivePipeline(
            planner=None,
            executor=executor,
            reviewer=FakeReviewer(),
            decision=AlwaysRetryDecision(),
            reasoning=FakeReasoning(),
            response_composer=FakeResponseComposer(),
            candidate_plan_generator=(
                FakeCandidatePlanGenerator()
            ),
            plan_validator=FakePlanValidator(),
            plan_scorer=FakePlanScorer(),
        )
        pipeline.MAX_ITERATIONS = 2
        state = CognitiveState(
            objective="exercise retry exhaustion",
        )

        response = await pipeline.run(
            messages=[
                ConversationMessage(
                    role="user",
                    content="exercise retry exhaustion",
                )
            ],
            state=state,
        )

        self.assertEqual(
            response.response,
            "timeout while calling tool",
        )
        self.assertEqual(
            state.final_response,
            "timeout while calling tool",
        )
        self.assertEqual(
            state.execution.attempt,
            2,
        )
        self.assertEqual(executor.calls, 2)
        self.assertEqual(len(state.execution.history), 2)


if __name__ == "__main__":
    unittest.main()
