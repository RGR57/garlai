import asyncio

from src.services.llm_service import LLMService


async def main():
    llm = LLMService()

    response = await llm.generate(
        system_prompt="You are a helpful assistant.",
        user_prompt="Reply with exactly: GARL works",
    )

    print(response)


asyncio.run(main())