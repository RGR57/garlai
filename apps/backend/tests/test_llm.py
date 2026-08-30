import asyncio
import json
import os
import unittest

import pytest

from src.services.llm_providers import FakeLLMProvider
from src.services.llm_service import LLMService


async def main():
    llm = LLMService()

    response = await llm.generate(
        [
            {
                "role": "system",
                "content": "You are a helpful assistant.",
            },
            {
                "role": "user",
                "content": "Reply with exactly: GARL works",
            },
        ],
        temperature=0,
        max_tokens=16,
    )

    print(response)


class FakeLLMProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_fake_llm_returns_reasoning_sections_for_reasoning_prompt(
        self,
    ):
        provider = FakeLLMProvider()

        response = await provider.generate(
            [
                {
                    "role": "system",
                    "content": "You are GARL's reasoning engine.",
                }
            ]
        )

        self.assertIn("OBJECTIVE:", response)
        self.assertIn("CONSTRAINTS:", response)
        self.assertIn("ASSUMPTIONS:", response)
        self.assertIn("STRATEGY:", response)

    async def test_fake_llm_returns_conversation_text_for_plain_prompt(
        self,
    ):
        provider = FakeLLMProvider()

        response = await provider.generate(
            [{"role": "user", "content": "hey"}]
        )

        self.assertEqual(response, "Hey! GARL is running.")

    async def test_fake_llm_returns_empty_memory_fixture_for_memory_prompt(
        self,
    ):
        provider = FakeLLMProvider()

        response = await provider.generate(
            [
                {
                    "role": "system",
                    "content": (
                        "You are GARL's long-term memory extraction engine."
                    ),
                }
            ]
        )

        self.assertEqual(json.loads(response), {"memories": []})


class LLMServiceProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_llm_service_uses_injected_provider_without_network(
        self,
    ):
        service = LLMService(provider=FakeLLMProvider())

        response = await service.generate(
            [{"role": "user", "content": "hey"}],
            temperature=0,
            max_tokens=16,
        )

        self.assertEqual(response, "Hey! GARL is running.")


@pytest.mark.skipif(
    os.environ.get("GARL_RUN_LIVE_LLM_TESTS") != "1",
    reason=(
        "Live LLM test is opt-in to avoid network and paid-provider "
        "calls during deterministic backend validation."
    ),
)
def test_live_llm_generate():
    asyncio.run(main())
