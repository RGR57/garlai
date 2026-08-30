import asyncio
import os

import pytest

from src.services.llm_service import LLMService


async def main():
    llm = LLMService()

    response = await llm.generate(
        system_prompt="You are a helpful assistant.",
        user_prompt="Reply with exactly: GARL works",
    )

    print(response)


@pytest.mark.skipif(
    os.environ.get("GARL_RUN_LIVE_LLM_TESTS") != "1",
    reason=(
        "Live LLM test is opt-in to avoid network and paid-provider "
        "calls during deterministic backend validation."
    ),
)
def test_live_llm_generate():
    asyncio.run(main())
