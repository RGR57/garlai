from typing import Any, Protocol


class LLMProvider(Protocol):
    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        ...


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
