from collections.abc import Awaitable, Callable
import json
from typing import Any, Protocol

from src.core.config import Settings
from src.services.llm_errors import (
    LLMCredentialsError,
    LLMConfigurationError,
    LLMMalformedResponseError,
    LLMModelUnavailableError,
    LLMProviderUnavailableError,
)


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
        settings: Settings | None = None,
        *,
        provider_name: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        completion: Callable[..., Awaitable[Any]] | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ):
        self.provider_name = (
            provider_name or (settings.LLM_PROVIDER if settings else "groq")
        ).strip().lower()
        self.model = model if model is not None else (
            settings.llm_model if settings else None
        )
        self.api_key = api_key if api_key is not None else (
            settings.GROQ_API_KEY if settings else ""
        )
        self.completion = completion
        self.timeout = timeout if timeout is not None else (
            settings.LLM_TIMEOUT_SECONDS if settings else 30.0
        )
        self.max_retries = max_retries if max_retries is not None else (
            settings.LLM_MAX_RETRIES if settings else 1
        )

    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        model = self._validate_configuration()
        completion = self.completion or self._get_completion()

        try:
            response = await completion(
                model=model,
                api_key=self.api_key,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self.timeout,
                num_retries=self.max_retries,
            )
        except (
            LLMCredentialsError,
            LLMConfigurationError,
            LLMMalformedResponseError,
            LLMModelUnavailableError,
            LLMProviderUnavailableError,
        ):
            raise
        except Exception as exc:
            raise self._normalize_exception(exc) from exc

        return self._extract_content(response)

    def _validate_configuration(self) -> str:
        if self.provider_name != "groq":
            raise LLMConfigurationError(
                "The configured LLM provider is unsupported.",
                code="unsupported_provider",
                provider=self.provider_name,
                model=self.model,
                retryable=False,
            )

        model = (self.model or "").strip()
        if not model:
            raise LLMConfigurationError(
                "The LLM model is not configured.",
                code="missing_model",
                provider=self.provider_name,
                model=None,
                retryable=False,
            )

        if not self.api_key.strip():
            raise LLMCredentialsError(
                "The LLM provider credential is not configured.",
                code="missing_credential",
                provider=self.provider_name,
                model=model,
                retryable=False,
            )

        if model.startswith("groq/"):
            return model
        return f"groq/{model}"

    @staticmethod
    def _get_completion() -> Callable[..., Awaitable[Any]]:
        from litellm import acompletion

        return acompletion

    def _extract_content(self, response: Any) -> str:
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise LLMMalformedResponseError(
                "The LLM provider returned a malformed response.",
                code="malformed_response",
                provider=self.provider_name,
                model=self.model,
                retryable=False,
            ) from exc

        if not isinstance(content, str):
            raise LLMMalformedResponseError(
                "The LLM provider returned a malformed response.",
                code="malformed_response",
                provider=self.provider_name,
                model=self.model,
                retryable=False,
            )

        return content.strip()

    def _normalize_exception(self, exc: Exception):
        message = str(exc).lower()

        if any(
            fragment in message
            for fragment in (
                "model_not_found",
                "does not exist",
                "not have access",
                "retired",
                "decommissioned",
            )
        ):
            return LLMModelUnavailableError(
                "The configured LLM model is unavailable.",
                code="model_unavailable",
                provider=self.provider_name,
                model=self.model,
                retryable=False,
            )

        if any(
            fragment in message
            for fragment in ("invalid api key", "unauthorized", "401", "authentication")
        ):
            return LLMCredentialsError(
                "The LLM provider rejected its credential.",
                code="invalid_credential",
                provider=self.provider_name,
                model=self.model,
                retryable=False,
            )

        if isinstance(exc, (ConnectionError, TimeoutError)) or any(
            fragment in message
            for fragment in (
                "timeout",
                "timed out",
                "rate limit",
                "429",
                "unavailable",
                "connection",
                "network",
                "server error",
                "502",
                "503",
                "504",
            )
        ):
            return LLMProviderUnavailableError(
                "The LLM provider is temporarily unavailable.",
                code="provider_unavailable",
                provider=self.provider_name,
                model=self.model,
                retryable=True,
            )

        return LLMProviderUnavailableError(
            "The LLM provider request failed.",
            code="provider_error",
            provider=self.provider_name,
            model=self.model,
            retryable=False,
        )


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
        normalized = joined.lower()

        if "reasoning engine" in normalized:
            return (
                "OBJECTIVE:\nRespond conversationally.\n\n"
                "CONSTRAINTS:\n- Do not use tools unnecessarily.\n\n"
                "ASSUMPTIONS:\n- The user is greeting GARL.\n\n"
                "STRATEGY:\nReturn a concise greeting."
            )

        if "long-term memory extraction engine" in normalized:
            return json.dumps({"memories": []})

        if "return only a valid garl execution plan" in normalized:
            if "install package" in normalized:
                return json.dumps(
                    {
                        "steps": [
                            {
                                "action": "install package",
                                "tool": "terminal",
                                "input": "pip install example-package",
                                "arguments": {
                                    "query": "pip install example-package"
                                },
                            }
                        ]
                    }
                )

            if "run rm -rf /" in normalized:
                return json.dumps(
                    {
                        "steps": [
                            {
                                "action": "run destructive command",
                                "tool": "terminal",
                                "input": "rm -rf /",
                                "arguments": {"query": "rm -rf /"},
                            }
                        ]
                    }
                )

            if "calculate 2 + 2" in normalized:
                return json.dumps(
                    {
                        "steps": [
                            {
                                "action": "calculate arithmetic result",
                                "tool": "calculator",
                                "input": "2 + 2",
                                "arguments": {"query": "2 + 2"},
                            }
                        ]
                    }
                )

            return json.dumps(
                {
                    "steps": [
                        {
                            "action": "respond conversationally",
                            "tool": None,
                            "input": "Reply to the user with a concise greeting.",
                            "arguments": {},
                        }
                    ]
                }
            )

        return "Hey! GARL is running."
