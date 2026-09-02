from copy import deepcopy

from src.models.cognitive_state import CognitiveState
from src.models.conversation import ConversationMessage
from src.models.plan import ExecutionPlan

from src.services.planner_service import PlannerService


class CandidatePlanGenerator:

    def __init__(
        self,
        planner: PlannerService,
    ):
        self.planner = planner

    async def generate(
        self,
        messages: list[ConversationMessage],
        state: CognitiveState,
        candidates: int = 2,
        *,
        eligible_tool_names: tuple[str, ...] | None = None,
        capability_guidance: str = "",
    ) -> list[ExecutionPlan]:

        plans: list[ExecutionPlan] = []

        strategies = self._strategies(
            candidates
        )

        for strategy in strategies:

            cloned_state = deepcopy(
                state
            )

            cloned_state.planner_notes.append(
                strategy
            )

            plan = await self.planner.create_plan(
                messages,
                cloned_state,
                eligible_tool_names=eligible_tool_names,
                capability_guidance=capability_guidance,
            )

            plans.append(
                plan
            )

        return self._deduplicate(
            plans
        )

    def _strategies(
        self,
        candidates: int,
    ) -> list[str]:

        defaults = [
            "Optimize for execution speed.",
            "Optimize for execution cost.",
            "Optimize for correctness.",
            "Optimize for information reuse.",
            "Optimize for overall balance.",
        ]

        return defaults[:candidates]

    def _deduplicate(
        self,
        plans: list[ExecutionPlan],
    ) -> list[ExecutionPlan]:

        unique: list[ExecutionPlan] = []

        seen: set[str] = set()

        for plan in plans:

            signature = self._signature(
                plan
            )

            if signature in seen:
                continue

            seen.add(
                signature
            )

            unique.append(
                plan
            )

        return unique

    def _signature(
        self,
        plan: ExecutionPlan,
    ) -> str:

        parts = []

        for step in plan.steps:

            parts.append(
                "|".join(
                    [
                        step.action,
                        str(step.tool),
                        step.input,
                        str(
                            sorted(
                                step.arguments.items()
                            )
                        ),
                    ]
                )
            )

        return "\n".join(
            parts
        )
