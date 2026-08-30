from typing import Any, Protocol

from src.core.config import Settings


class LLMProvider(Protocol):
    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        ...


class LiteLLMProvider:
    def __init__(
        self,
        settings: Settings,
    ):
        self.settings = settings

    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        from litellm import acompletion

        response = await acompletion(
            model=self.settings.llm_model,
            api_key=self.settings.GROQ_API_KEY,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.settings.LLM_TIMEOUT_SECONDS,
            num_retries=self.settings.LLM_MAX_RETRIES,
        )

        content = response.choices[0].message.content
        if content is None:
            return ""

        return content.strip()


class FakeLLMProvider:
    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        joined = "\n".join(
            str(message.get("content", ""))
            for message in messages
        )

        if "reasoning engine" in joined:
            return (
                "OBJECTIVE:\nRespond conversationally.\n\n"
                "CONSTRAINTS:\n- Do not use tools unnecessarily.\n\n"
                "ASSUMPTIONS:\n- The user is greeting GARL.\n\n"
                "STRATEGY:\nReturn a concise greeting."
            )

        return "Hey! GARL is running."
