from typing import Any

from litellm import acompletion

from src.core.config import settings


class LLMService:

    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        """
        Sends a single request to the configured LLM and returns only
        the assistant's final response.

        NOTE:
        - Planning/review loops are handled by CognitivePipeline.
        - This service performs exactly one LLM inference.
        """

        response = await acompletion(
            model=settings.MODEL_NAME,
            api_key=settings.GROQ_API_KEY,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content

        if content is None:
            return ""

        return content.strip()