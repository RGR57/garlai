import json
import re

from src.models.memory import MemoryType
from src.services.llm_service import LLMService
from src.utils.logger import logger


MEMORY_EXTRACTION_PROMPT = """
You are GARL's long-term memory extraction engine.

Your job is to identify durable information explicitly stated
by the USER that may be useful in future interactions.

A memory must represent information that the user actually
provided. Never infer, guess, assume, or invent missing facts.

GOOD MEMORIES:

- stable user preferences
- explicit user decisions
- durable project facts
- technical constraints
- long-term goals
- important reusable context
- confirmed results that will matter later

EXAMPLES:

User:
"For GARL I prefer Python for backend development."

Valid memory:
{
    "content": "Prefers Python for GARL backend development",
    "memory_type": "preference",
    "importance": 0.8
}

User:
"GARL must require approval before modifying source code."

Valid memory:
{
    "content": "GARL must require approval before modifying source code",
    "memory_type": "decision",
    "importance": 0.9
}

DO NOT STORE:

- questions
- requests for information
- greetings
- temporary commands
- approval/rejection messages
- one-time tool instructions
- casual filler
- guesses or inferred information
- unanswered questions
- uncertainty
- information not explicitly provided by the user
- placeholders such as "unknown", "unspecified", or
  "not provided"
- information useful only for the current action

IMPORTANT:

A question asking about an existing preference or fact does NOT
create a new memory.

Example:

User:
"What backend language do I prefer?"

This does NOT state a preference.

Return:

{
    "memories": []
}

Never create a memory containing values such as:

- unknown
- unspecified
- not specified
- not provided
- unclear
- none
- N/A

Return ONLY valid JSON.

Required schema:

{
    "memories": [
        {
            "content": "string",
            "memory_type": "fact|preference|decision|context|result",
            "importance": 0.0
        }
    ]
}

importance must be between 0.0 and 1.0.

If nothing should be remembered, return exactly:

{
    "memories": []
}

Do not include markdown.
Do not explain your response.
"""


class MemoryExtractor:

    INVALID_MEMORY_VALUES = {
        "unknown",
        "unspecified",
        "not specified",
        "not provided",
        "not known",
        "unclear",
        "none",
        "n/a",
        "na",
        "undefined",
        "not available",
        "no preference",
        "no preference specified",
    }

    QUESTION_PREFIXES = (
        "what ",
        "which ",
        "who ",
        "where ",
        "when ",
        "why ",
        "how ",
        "do ",
        "does ",
        "did ",
        "can ",
        "could ",
        "would ",
        "should ",
        "is ",
        "are ",
        "am ",
        "was ",
        "were ",
        "have ",
        "has ",
        "had ",
        "will ",
    )

    def __init__(
        self,
        llm: LLMService,
    ):
        self.llm = llm

    async def extract(
        self,
        user_message: str,
    ) -> list[dict]:

        if not self._should_analyze(
            user_message
        ):
            logger.info(
                "Memory extraction skipped by fast filter."
            )

            return []

        prompt = [
            {
                "role": "system",
                "content": MEMORY_EXTRACTION_PROMPT,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ]

        try:

            response = await self.llm.generate(
                prompt
            )

            logger.info(
                "Memory extractor raw response: "
                f"{response}"
            )

            data = self._parse_response(
                response
            )

            return self._validate_memories(
                data
            )

        except Exception as exc:

            # Memory extraction must never break
            # the main cognitive pipeline.

            logger.warning(
                "Memory extraction failed: "
                f"{exc}"
            )

            return []

    # ==========================================================
    # PARSING
    # ==========================================================

    def _parse_response(
        self,
        response: str,
    ) -> dict:

        response = response.strip()

        # Handle accidental markdown/code fences or
        # surrounding LLM text.

        match = re.search(
            r"\{.*\}",
            response,
            re.DOTALL,
        )

        if match:
            response = match.group(0)

        data = json.loads(
            response
        )

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "Memory extraction response "
                "must be an object."
            )

        return data

    # ==========================================================
    # VALIDATION
    # ==========================================================

    def _validate_memories(
        self,
        data: dict,
    ) -> list[dict]:

        raw_memories = data.get(
            "memories",
            [],
        )

        if not isinstance(
            raw_memories,
            list,
        ):
            raise ValueError(
                "'memories' must be a list."
            )

        valid_memories = []

        allowed_types = {
            memory_type.value
            for memory_type
            in MemoryType
        }

        for raw_memory in raw_memories:

            if not isinstance(
                raw_memory,
                dict,
            ):
                continue

            content = str(
                raw_memory.get(
                    "content",
                    "",
                )
            ).strip()

            if not content:
                continue

            # --------------------------------------------------
            # REJECT LOW-QUALITY / PLACEHOLDER MEMORIES
            # --------------------------------------------------

            if self._is_invalid_memory_content(
                content
            ):

                logger.info(
                    "Rejected invalid memory candidate: "
                    f"{content}"
                )

                continue

            memory_type = str(
                raw_memory.get(
                    "memory_type",
                    MemoryType.CONTEXT.value,
                )
            ).strip().lower()

            if (
                memory_type
                not in allowed_types
            ):
                memory_type = (
                    MemoryType.CONTEXT.value
                )

            try:

                importance = float(
                    raw_memory.get(
                        "importance",
                        0.5,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                importance = 0.5

            importance = max(
                0.0,
                min(
                    1.0,
                    importance,
                ),
            )

            valid_memories.append(
                {
                    "content": content,
                    "memory_type": memory_type,
                    "importance": importance,
                }
            )

        return valid_memories

    # ==========================================================
    # INVALID MEMORY DETECTION
    # ==========================================================

    def _is_invalid_memory_content(
        self,
        content: str,
    ) -> bool:

        normalized = (
            content
            .strip()
            .lower()
        )

        if normalized in self.INVALID_MEMORY_VALUES:
            return True

        # Reject extremely weak memory content.
        if len(normalized) < 3:
            return True

        # Catch common generated placeholders such as:
        # "Preference is unknown"
        # "Backend language not specified"

        invalid_phrases = (
            "is unknown",
            "is unspecified",
            "not specified",
            "not provided",
            "not known",
            "cannot determine",
            "can't determine",
            "no information",
            "no preference",
        )

        if any(
            phrase in normalized
            for phrase in invalid_phrases
        ):
            return True

        return False

    # ==========================================================
    # FAST FILTER
    # ==========================================================

    def _should_analyze(
        self,
        message: str,
    ) -> bool:

        normalized = (
            message
            .strip()
            .lower()
        )

        if not normalized:
            return False

        ignored_messages = {
            "hi",
            "hello",
            "hey",
            "approve",
            "approved",
            "reject",
            "rejected",
            "yes",
            "no",
            "ok",
            "okay",
            "thanks",
            "thank you",
        }

        if normalized in ignored_messages:
            return False

        # Very short messages are usually poor
        # long-term memory candidates.

        if len(normalized) < 8:
            return False

        # ------------------------------------------------------
        # PURE QUESTIONS
        # ------------------------------------------------------
        #
        # Questions generally request existing information;
        # they do not establish new durable facts.
        #
        # Example:
        # "What backend language do I prefer?"
        #
        # This should retrieve memory, not create memory.

        if normalized.endswith("?"):
            return False

        if normalized.startswith(
            self.QUESTION_PREFIXES
        ):
            return False

        return True