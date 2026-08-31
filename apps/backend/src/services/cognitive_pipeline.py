from src.models.decision import DecisionType
from src.models.execution_trace import (
    ExecutionEventType,
)

from src.services.decision_service import (
    DecisionService,
)
from src.services.executor_service import (
    ExecutorService,
)
from src.services.planner_service import (
    PlannerService,
)
from src.services.reasoning_service import (
    ReasoningService,
)
from src.services.reviewer_service import (
    ReviewerService,
)

from src.services.response_composer import (
    ResponseComposer,
)
from src.models.chat_response import (
    ChatResponse,
)

from src.models.cognitive_state import (
    CognitiveState,
)

from src.models.conversation import (
    ConversationMessage,
)

from src.utils.logger import (
    logger,
)
from src.services.candidate_plan_generator import (
    CandidatePlanGenerator,
)
from src.services.plan_scorer import (
    PlanScorer,
)
from src.services.plan_validator import (
    PlanValidator,
)

class CognitivePipeline:

    MAX_ITERATIONS = 5

    def __init__(
        self,
        planner: PlannerService,
        executor: ExecutorService,
        reviewer: ReviewerService,
        decision: DecisionService,
        reasoning: ReasoningService,
        response_composer: ResponseComposer,
        candidate_plan_generator: CandidatePlanGenerator,
        plan_validator: PlanValidator,
        plan_scorer: PlanScorer,
    ):
        self.planner = planner
        self.executor = executor
        self.reviewer = reviewer
        self.decision = decision
        self.reasoning = reasoning
        self.response_composer = (
            response_composer
        )
        self.candidate_plan_generator = (
        candidate_plan_generator
        )

        self.plan_validator = (
            plan_validator
        )

        self.plan_scorer = (
            plan_scorer
        )

    async def run_persisted_step(
        self,
        *,
        execution_id: str,
        step_id: int,
        messages: list[ConversationMessage],
        state: CognitiveState,
    ) -> ChatResponse:
        """Execute one recovered cursor without regenerating its validated plan."""
        result = await self.executor.execute_ready_step(
            execution_id,
            step_id,
            messages,
            state.execution,
        )
        state.execution.current_step = step_id
        state.execution.record(result)
        if result.success:
            state.execution.variables[f"step{step_id}"] = result.output
            return ChatResponse(response=str(result.output))
        return ChatResponse(
            response=result.error or "Persisted step execution failed."
        )

    async def run(
        self,
        messages: list[ConversationMessage],
        state: CognitiveState,
        knowledge_context: str = "",
    ) -> ChatResponse:

        if knowledge_context:

            logger.info(
                "Knowledge context injected "
                f"({len(knowledge_context)} chars)."
            )

            state.knowledge_context = (
                knowledge_context
            )

        chat_response = ChatResponse(
            response="",
        )

        final_response = (
            state.final_response
            or "Execution did not produce a final response."
        )

        # ======================================================
        # REASONING
        # ======================================================

        if not state.reasoning.nodes:

            logger.info(
                "Running reasoning engine."
            )

            if state.knowledge_context:

                logger.info(
                    "Reasoning received "
                    f"{len(state.knowledge_context)} "
                    "knowledge characters."
                )

            state.reasoning = (
                await self.reasoning.analyze(
                    state
                )
            )
            logger.info(
    "========== REASONING =========="
            )

            for node in state.reasoning.nodes:

                reasoning_type = (
                    node.reasoning_type.value.upper()
                )

                logger.info(
                    f"[{reasoning_type}] "
                    f"{node.thought}"
                )

                if reasoning_type == "OBJECTIVE":
                    event = (
                        ExecutionEventType.OBJECTIVE
                    )

                elif reasoning_type == "CONSTRAINT":
                    event = (
                        ExecutionEventType.CONSTRAINT
                    )

                elif reasoning_type == "ASSUMPTION":
                    event = (
                        ExecutionEventType.ASSUMPTION
                    )

                elif reasoning_type == "STRATEGY":
                    event = (
                        ExecutionEventType.STRATEGY
                    )

                else:
                    event = (
                        ExecutionEventType.REASONING
                    )

                state.execution_trace.add(
                    event_type=event,
                    message=node.thought,
                    metadata={
                        "iteration": state.iteration,
                    },
                )

            logger.info(
                "=============================="
            )

        # ======================================================
        # COGNITIVE LOOP
        # ======================================================

        for iteration in range(
            self.MAX_ITERATIONS
        ):

            state.iteration = iteration + 1

            logger.info(
                f"Cognitive iteration "
                f"{state.iteration}/"
                f"{self.MAX_ITERATIONS}"
            )

            state.execution.begin_attempt()

            logger.info(
                f"Execution attempt "
                f"{state.execution.attempt}"
            )

            # ==================================================
            # PLANNER
            # ==================================================

            logger.info(
                "Creating execution plan candidates."
            )

            candidate_plans = (
                await self.candidate_plan_generator.generate(
                    messages,
                    state,
                    candidates=1,
                )
            )

            if not candidate_plans:

                raise RuntimeError(
                    "Planner failed to generate "
                    "any execution plan."
                )

            # ==================================================
            # PLAN VALIDATION
            # ==================================================

            valid_candidates = []

            for candidate_index, candidate in enumerate(
                candidate_plans,
                start=1,
            ):

                validation = (
                    self.plan_validator.validate(
                        candidate,
                        state,
                    )
                )

                logger.info(
                    f"Candidate {candidate_index} "
                    f"validation: "
                    f"valid={validation.valid}, "
                    f"score={validation.score}"
                )

                if validation.errors:

                    for error in validation.errors:

                        logger.warning(
                            f"Candidate "
                            f"{candidate_index} "
                            f"validation error: "
                            f"{error}"
                        )

                if validation.warnings:

                    for warning in validation.warnings:

                        logger.warning(
                            f"Candidate "
                            f"{candidate_index} "
                            f"validation warning: "
                            f"{warning}"
                        )

                if validation.valid:

                    valid_candidates.append(
                        (
                            candidate,
                            validation,
                        )
                    )

            if not valid_candidates:

                raise RuntimeError(
                    "All generated execution plans "
                    "failed validation."
                )

            # ==================================================
            # PLAN SCORING
            # ==================================================

            scored_candidates = []

            for candidate, validation in (
                valid_candidates
            ):

                plan_score = (
                    self.plan_scorer.score(
                        candidate,
                        state,
                    )
                )

                logger.info(
                    f"Plan score: "
                    f"{plan_score.score}"
                )

                logger.info(
                    f"Plan breakdown: "
                    f"{plan_score.breakdown}"
                )

                scored_candidates.append(
                    (
                        candidate,
                        plan_score,
                    )
                )

            # ==================================================
            # BEST PLAN SELECTION
            # ==================================================

            scored_candidates.sort(
                key=lambda item: item[1].score,
                reverse=True,
            )

            plan, selected_score = (
                scored_candidates[0]
            )

            logger.info(
                f"Selected plan with score "
                f"{selected_score.score}"
            )

            for step in plan.steps:

                logger.info(
                    f"Plan step "
                    f"{step.id}: "
                    f"action={step.action}, "
                    f"tool={step.tool}, "
                    f"input={step.input}"
                )

            state.execution_trace.add(
                event_type=ExecutionEventType.PLAN_CREATED,
                message=(
                    f"Generated and validated "
                    f"{len(candidate_plans)} "
                    f"candidate plan(s). "
                    f"Selected plan with score "
                    f"{selected_score.score}."
                ),
                metadata={
                    "iteration": state.iteration,
                    "attempt": state.execution.attempt,
                    "candidate_count": len(
                        candidate_plans
                    ),
                    "valid_candidate_count": len(
                        valid_candidates
                    ),
                    "selected_score": (
                        selected_score.score
                    ),
                    "score_breakdown": (
                        selected_score.breakdown
                    ),
                },
            )

            # ==================================================
            # EXECUTION
            # ==================================================

            await self.executor.execute(
                messages,
                plan,
                state.execution,
            )

            last = state.execution.last_result()

            if last:

                observation = (
                    str(last.output)
                    if last.success
                    else (
                        last.error
                        or "Execution failed."
                    )
                )

                state.execution_trace.add(
                    event_type=ExecutionEventType.STEP_COMPLETED,
                    message=observation,
                    metadata={
                        "step": last.step_id,
                        "success": last.success,
                        "iteration": state.iteration,
                    },
                )

                state.planner_notes.append(
                    f"Iteration "
                    f"{state.iteration}: "
                    f"success={last.success}"
                )

            # ==================================================
            # REVIEW
            # ==================================================
            # ==================================================
            # REVIEW
            # ==================================================

            success, review_response = (
                await self.reviewer.review(
                    state.execution
                )
            )

            state.reviewer_notes.append(
                review_response
            )

            logger.info(
                f"Review: success={success}"
            )

            if success:

                chat_response = (
                    await self.response_composer.compose(
                        state.execution
                    )
                )

                state.final_response = (
                    chat_response.response
                )

                final_response = (
                    state.final_response
                )

                state.artifacts = (
                    chat_response.artifacts
                )

            else:

                chat_response = ChatResponse(
                    response=review_response,
                )

                state.final_response = (
                    review_response
                )

                final_response = (
                    state.final_response
                )
            # ==================================================
            # SUCCESS
            # ==================================================

            if success:

                logger.info(
                    "Execution succeeded."
                )

                state.execution_trace.add(
                    event_type=ExecutionEventType.FINAL_RESULT,
                    message=state.final_response,
                    metadata={
                        "success": True,
                        "iteration": state.iteration,
                        "attempt": state.execution.attempt,
                    },
                )

                # state.final_response = (
                #     final_response
                # )

                return chat_response

            # ==================================================
            # DECISION ENGINE
            # ==================================================

            decision = await self.decision.decide(
                state.execution
            )

            logger.info(
                f"Decision: "
                f"{decision.action.value}"
            )

            logger.info(
                f"Reason: "
                f"{decision.reason}"
            )

            state.execution_trace.add(
                event_type=ExecutionEventType.DECISION,
                message=decision.reason,
                metadata={
                    "decision": (
                        decision.action.value
                    ),
                    "iteration": (
                        state.iteration
                    ),
                    "attempt": (
                        state.execution.attempt
                    ),
                },
            )

            # ==================================================
            # RETURN
            # ==================================================

            if (
                decision.action
                == DecisionType.RETURN
            ):

                state.execution_trace.add(
                    event_type=ExecutionEventType.FINAL_RESULT,
                    message=state.final_response,
                    metadata={
                        "success": False,
                        "iteration": (
                            state.iteration
                        ),
                        "attempt": (
                            state.execution.attempt
                        ),
                    },
                )

                # state.final_response = (
                #     final_response
                # )

                return ChatResponse(
                    response=state.final_response,
                    artifacts=state.artifacts,
                )

            # ==================================================
            # APPROVAL
            # ==================================================

            if (
                decision.action
                == DecisionType.WAIT_FOR_APPROVAL
            ):

                final_response = (
                    "Approval required: "
                    f"{state.execution.approval_reason}"
                )

                state.final_response = (
                    final_response
                )

                logger.info(
                    "Waiting for approval."
                )

                state.execution_trace.add(
                    event_type=(
                        ExecutionEventType
                        .APPROVAL_REQUIRED
                    ),
                    message=final_response,
                    metadata={
                        "tool": (
                            state.execution.pending_tool
                        ),
                        "risk": (
                            state.execution.risk_level
                        ),
                        "iteration": (
                            state.iteration
                        ),
                        "attempt": (
                            state.execution.attempt
                        ),
                    },
                )

                # state.final_response = (
                #     final_response
                # )

                return ChatResponse(
                    response=final_response,
                    artifacts=state.artifacts,
                )

            # ==================================================
            # RETRY
            # ==================================================

            if (
                decision.action
                == DecisionType.RETRY
            ):

                logger.info(
                    "Retry requested."
                )

                state.execution_trace.add(
                    event_type=ExecutionEventType.RETRY,
                    message=decision.reason,
                    metadata={
                        "iteration": (
                            state.iteration
                        ),
                        "attempt": (
                            state.execution.attempt
                        ),
                    },
                )

                continue

            # ==================================================
            # REPLAN
            # ==================================================

            if (
                decision.action
                == DecisionType.REPLAN
            ):

                logger.info(
                    "Replan requested."
                )

                state.execution_trace.add(
                    event_type=ExecutionEventType.REPLAN,
                    message=decision.reason,
                    metadata={
                        "iteration": (
                            state.iteration
                        ),
                        "attempt": (
                            state.execution.attempt
                        ),
                    },
                )

                continue

            # ==================================================
            # UNKNOWN DECISION
            # ==================================================

            logger.warning(
                "Unknown decision."
            )

            state.execution_trace.add(
                event_type=ExecutionEventType.ERROR,
                message=(
                    "Unknown decision "
                    "returned."
                ),
                metadata={
                    "decision": (
                        str(
                            decision.action
                        )
                    )
                },
            )

            break

        # ======================================================
        # MAX ITERATIONS
        # ======================================================

        logger.warning(
            "Maximum iterations reached."
        )

        state.execution_trace.add(
            event_type=ExecutionEventType.ERROR,
            message=(
                "Maximum cognitive "
                "iterations reached."
            ),
            metadata={
                "max_iterations": (
                    self.MAX_ITERATIONS
                )
            },
        )

        state.execution_trace.add(
            event_type=ExecutionEventType.FINAL_RESULT,
            message=final_response,
            metadata={
                "success": False,
                "reason": "max_iterations",
            },
        )

        state.final_response = (
            final_response
        )

        return ChatResponse(
            response=state.final_response,
            artifacts=state.artifacts,
        )
