from typing import Any

from src.core.config import settings
from src.services.llm_providers import (
    LiteLLMProvider,
    LLMProvider,
)
from src.services.llm_errors import LLMMalformedResponseError


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

        response = await self.provider.generate(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if not isinstance(response, str):
            raise LLMMalformedResponseError(
                "The LLM provider returned a malformed response.",
                code="malformed_response",
                provider="injected",
                model=None,
                retryable=False,
            )

        return response
