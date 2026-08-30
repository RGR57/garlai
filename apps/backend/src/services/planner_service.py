from src.models.cognitive_state import CognitiveState
from src.models.conversation import ConversationMessage
from src.models.plan import ExecutionPlan

from src.prompts.planner_prompt import PLANNER_PROMPT

from src.services.llm_service import LLMService
from src.services.plan_parser import PlanParser
from src.services.prompt_builder import PromptBuilder
from src.services.tool_catalog import ToolCatalog

from src.utils.logger import logger


class PlannerService:

    MAX_PARSE_ATTEMPTS = 3

    def __init__(
        self,
        llm: LLMService,
        parser: PlanParser,
        prompt_builder: PromptBuilder,
        tool_catalog: ToolCatalog,
    ):
        self.llm = llm
        self.parser = parser
        self.prompt_builder = prompt_builder
        self.tool_catalog = tool_catalog

    async def create_plan(
        self,
        messages: list[ConversationMessage],
        state: CognitiveState,
    ) -> ExecutionPlan:

        available_tools = (
            self.tool_catalog.get_tool_descriptions()
        )

        reviewer_feedback = (
            self._build_reviewer_feedback(
                state
            )
        )

        planner_feedback = (
            self._build_planner_feedback(
                state
            )
        )

        execution_feedback = (
            self._build_execution_feedback(
                state
            )
        )

        reasoning_feedback = (
            self._build_reasoning(
                state
            )
        )

        planner_system_prompt = f"""
{PLANNER_PROMPT}

AVAILABLE TOOLS

{available_tools}

==================================================

CURRENT OBJECTIVE:

{state.objective}

==================================================

KNOWLEDGE CONTEXT

{state.knowledge_context if state.knowledge_context else "None"}

==================================================

COGNITIVE REASONING

{self._build_reasoning(state)}

==================================================

CURRENT ITERATION

{state.iteration}

EXECUTION ATTEMPT

{state.execution.attempt}

==================================================

PREVIOUS EXECUTION RESULTS

{execution_feedback}

==================================================

PREVIOUS REVIEWER FEEDBACK

{reviewer_feedback}

==================================================

PREVIOUS PLANNER NOTES

{planner_feedback}

==================================================

RECOVERY RULES

1. Examine previous execution failures before creating
   the next plan.

2. Never repeat a deterministic failed action using
   the same tool and arguments.

3. Never fabricate tool outputs or assume a tool
   succeeded before execution.

4. Reuse previous successful outputs whenever they
   help complete the objective.

5. Replan intelligently after failure by choosing
   a different valid strategy.

6. Produce the smallest valid execution plan needed
   to accomplish the objective.

7. Use Knowledge Context whenever it directly helps
   complete the objective.

8. If Knowledge Context conflicts with assumptions,
   prefer the retrieved knowledge.

9. Return ONLY a valid GARL execution plan in the
   required JSON schema.
"""

        prompt = self.prompt_builder.build(
            system_prompt=planner_system_prompt,
            messages=messages,
            state=state,
        )

        last_error = None

        for attempt in range(
            self.MAX_PARSE_ATTEMPTS
        ):

            logger.info(
                f"Planner attempt "
                f"{attempt+1}/"
                f"{self.MAX_PARSE_ATTEMPTS}"
            )

            response = await self.llm.generate(
                prompt
            )

            logger.info(
                f"Planner raw response: "
                f"{response}"
            )

            try:

                plan = self.parser.parse(
                    response
                )

                logger.info(
                    f"Planner generated "
                    f"{len(plan.steps)} step(s)."
                )

                for step in plan.steps:

                    logger.info(
                        f"Plan step "
                        f"{step.id}: "
                        f"action={step.action}, "
                        f"tool={step.tool}, "
                        f"input={step.input}"
                    )

                return plan

            except Exception as exc:

                last_error = exc

                logger.warning(
                    f"Planner parse failed "
                    f"attempt {attempt+1}: "
                    f"{exc}"
                )

                prompt.append(
                    {
                        "role": "system",
                        "content": (
                            "Return ONLY valid JSON. "
                            "No markdown. "
                            "No explanation."
                        ),
                    }
                )

        raise RuntimeError(
            "Planner failed after "
            f"{self.MAX_PARSE_ATTEMPTS} attempts. "
            f"{last_error}"
        )
        # ======================================================
    # EXECUTION FEEDBACK
    # ======================================================

    def _build_execution_feedback(
        self,
        state: CognitiveState,
    ) -> str:

        history = state.execution.history

        if not history:
            return "None"

        feedback = []

        for result in history:

            status = (
                "SUCCESS"
                if result.success
                else "FAILED"
            )

            parts = [
                f"Step {result.step_id}",
                f"Status: {status}",
            ]

            if result.output is not None:

                parts.append(
                    f"Output: {result.output}"
                )

            if result.error:

                parts.append(
                    f"Error: {result.error}"
                )

            feedback.append(
                " | ".join(parts)
            )

        return "\n".join(
            feedback
        )

    # ======================================================
    # REVIEWER FEEDBACK
    # ======================================================

    def _build_reviewer_feedback(
        self,
        state: CognitiveState,
    ) -> str:

        if not state.reviewer_notes:
            return "None"

        return "\n".join(
            f"- {note}"
            for note in state.reviewer_notes
        )

    # ======================================================
    # PLANNER FEEDBACK
    # ======================================================

    def _build_planner_feedback(
        self,
        state: CognitiveState,
    ) -> str:

        if not state.planner_notes:
            return "None"

        return "\n".join(
            f"- {note}"
            for note in state.planner_notes
        )
        # ======================================================
    # REASONING
    # ======================================================

    def _build_reasoning(
        self,
        state: CognitiveState,
    ) -> str:

        reasoning = state.reasoning

        if (
            reasoning is None
            or not reasoning.nodes
        ):
            return "None"

        sections: dict[
            str,
            list[str]
        ] = {}

        for node in reasoning.nodes:

            section = (
                node.reasoning_type.value
                .upper()
            )

            sections.setdefault(
                section,
                []
            ).append(
                node.thought
            )

        output: list[str] = []

        ordered_sections = [
            "OBJECTIVE",
            "CONSTRAINT",
            "ASSUMPTION",
            "STRATEGY",
        ]

        for section in ordered_sections:

            if section not in sections:
                continue

            output.append(
                f"{section}:"
            )

            for thought in sections[
                section
            ]:

                output.append(
                    f"- {thought}"
                )

            output.append("")

        # Any future reasoning types
        # are appended automatically.

        for section, thoughts in sections.items():

            if section in ordered_sections:
                continue

            output.append(
                f"{section}:"
            )

            for thought in thoughts:

                output.append(
                    f"- {thought}"
                )

            output.append("")

        return "\n".join(output)
