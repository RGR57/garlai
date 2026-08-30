import unittest
from types import SimpleNamespace

from src.services.llm_errors import (
    LLMCredentialsError,
    LLMMalformedResponseError,
    LLMConfigurationError,
    LLMModelUnavailableError,
    LLMProviderUnavailableError,
)
from src.services.llm_providers import LiteLLMProvider
from src.services.llm_service import LLMService


async def raises_model_error(**kwargs):
    raise Exception("model_not_found: model does not exist")


async def raises_key_error(**kwargs):
    raise Exception("Invalid API Key: secret")


async def raises_network_error(**kwargs):
    raise TimeoutError("connection timed out")


async def returns_malformed_response(**kwargs):
    return object()


async def returns_text_response(**kwargs):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=" GARL response "),
            )
        ]
    )


class NonTextProvider:
    async def generate(self, messages, *, temperature=0.2, max_tokens=None):
        return None


class LiteLLMProviderErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_litellm_provider_rejects_missing_credential(self):
        provider = LiteLLMProvider(
            provider_name="groq",
            model="groq/openai/gpt-oss-120b",
            api_key="",
            completion=raises_model_error,
        )

        with self.assertRaises(LLMCredentialsError) as exc:
            await provider.generate([{"role": "user", "content": "hey"}])

        self.assertEqual(exc.exception.code, "missing_credential")
        self.assertFalse(exc.exception.retryable)

    async def test_litellm_provider_rejects_unsupported_provider(self):
        provider = LiteLLMProvider(
            provider_name="unsupported",
            model="model",
            api_key="secret",
            completion=raises_model_error,
        )

        with self.assertRaises(LLMConfigurationError) as exc:
            await provider.generate([{"role": "user", "content": "hey"}])

        self.assertEqual(exc.exception.code, "unsupported_provider")

    async def test_litellm_provider_adds_groq_prefix_at_provider_boundary(self):
        observed_models = []

        async def completion(**kwargs):
            observed_models.append(kwargs["model"])
            return await returns_text_response()

        provider = LiteLLMProvider(
            provider_name="groq",
            model="openai/gpt-oss-120b",
            api_key="secret",
            completion=completion,
        )

        response = await provider.generate([{"role": "user", "content": "hey"}])

        self.assertEqual(response, "GARL response")
        self.assertEqual(observed_models, ["groq/openai/gpt-oss-120b"])

    async def test_litellm_provider_maps_model_not_found(self):
        provider = LiteLLMProvider(
            provider_name="groq",
            model="groq/missing-model",
            api_key="secret",
            completion=raises_model_error,
        )

        with self.assertRaises(LLMModelUnavailableError) as exc:
            await provider.generate([{"role": "user", "content": "hey"}])

        self.assertEqual(exc.exception.code, "model_unavailable")
        self.assertFalse(exc.exception.retryable)

    async def test_litellm_provider_maps_invalid_api_key_without_secret(self):
        provider = LiteLLMProvider(
            provider_name="groq",
            model="groq/openai/gpt-oss-120b",
            api_key="secret",
            completion=raises_key_error,
        )

        with self.assertRaises(LLMCredentialsError) as exc:
            await provider.generate([{"role": "user", "content": "hey"}])

        self.assertEqual(exc.exception.code, "invalid_credential")
        self.assertNotIn("secret", str(exc.exception))

    async def test_litellm_provider_maps_timeout_to_retryable_provider_error(self):
        provider = LiteLLMProvider(
            provider_name="groq",
            model="groq/openai/gpt-oss-120b",
            api_key="secret",
            completion=raises_network_error,
        )

        with self.assertRaises(LLMProviderUnavailableError) as exc:
            await provider.generate([{"role": "user", "content": "hey"}])

        self.assertEqual(exc.exception.code, "provider_unavailable")
        self.assertTrue(exc.exception.retryable)

    async def test_litellm_provider_rejects_malformed_completion_response(self):
        provider = LiteLLMProvider(
            provider_name="groq",
            model="groq/openai/gpt-oss-120b",
            api_key="secret",
            completion=returns_malformed_response,
        )

        with self.assertRaises(LLMMalformedResponseError):
            await provider.generate([{"role": "user", "content": "hey"}])


class LLMServiceResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_llm_service_rejects_non_text_provider_result(self):
        service = LLMService(provider=NonTextProvider())

        with self.assertRaises(LLMMalformedResponseError):
            await service.generate([{"role": "user", "content": "hey"}])
