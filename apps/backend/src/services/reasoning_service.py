from src.models.cognitive_state import CognitiveState
from src.models.reasoning import (
    ReasoningChain,
    ReasoningType,
)
from src.services.llm_service import LLMService
from src.utils.logger import logger


class ReasoningService:

    def __init__(
        self,
        llm: LLMService,
    ):
        self.llm = llm

    async def analyze(
        self,
        state: CognitiveState,
    ) -> ReasoningChain:

        messages = [
            {
                "role": "system",
                "content": (
                    "You are GARL's reasoning engine."
                ),
            },
            {
                "role": "user",
                "content": f"""
Analyze the user's objective before planning.

User Objective:
{state.objective}

Knowledge Context:
{state.knowledge_context if state.knowledge_context else "None"}

Return exactly four sections.

OBJECTIVE:
(one sentence)

CONSTRAINTS:
(bullet list)

ASSUMPTIONS:
(bullet list)

STRATEGY:
(one paragraph)

Rules:

- Do NOT generate an execution plan.
- Do NOT call tools.
- Do NOT solve the user's request.
- Use the Knowledge Context whenever it is relevant.
- If the Knowledge Context is empty or unrelated, ignore it.
- Be concise.
""",
            },
        ]

        response = await self.llm.generate(
            messages
        )

        logger.info(
            "Reasoning raw response:\n%s",
            response,
        )

        chain = ReasoningChain()

        current = None

        for raw_line in response.splitlines():

            line = raw_line.strip()

            if not line:
                continue

            line = (
                line
                .lstrip("#")
                .strip()
            )

            upper = line.upper()

            if upper.startswith(
                "OBJECTIVE"
            ):
                current = (
                    ReasoningType.OBJECTIVE
                )
                continue

            if upper.startswith(
                "CONSTRAINT"
            ):
                current = (
                    ReasoningType.CONSTRAINT
                )
                continue

            if upper.startswith(
                "ASSUMPTION"
            ):
                current = (
                    ReasoningType.ASSUMPTION
                )
                continue

            if upper.startswith(
                "STRATEGY"
            ):
                current = (
                    ReasoningType.STRATEGY
                )
                continue

            if current is None:
                continue

            line = (
                line
                .lstrip("-")
                .lstrip("*")
                .lstrip("•")
                .strip()
            )

            if not line:
                continue

            chain.add(
                thought=line,
                reasoning_type=current,
            )

        logger.info(
            "Parsed %d reasoning nodes.",
            len(chain.nodes),
        )

        for node in chain.nodes:

            logger.info(
                "[%s] %s",
                node.reasoning_type.value.upper(),
                node.thought,
            )

        return chain