from typing import Any

from src.core.config import settings
from src.services.llm_providers import (
    LiteLLMProvider,
    LLMProvider,
)


class LLMService:
    def __init__(
        self,
        provider: LLMProvider | None = None,
    ):
        self.provider = provider or LiteLLMProvider(settings)

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

        return await self.provider.generate(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
