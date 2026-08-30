import json

from src.services.llm_service import LLMService

from .prompts import SYSTEM_PROMPT
from .schemas import Plan


class Planner:

    def __init__(self):
        self.llm = LLMService()

    async def plan(self, objective: str) -> Plan:

        response = await self.llm.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=objective,
        )

        plan = Plan.model_validate(
            json.loads(response)
        )

        return plan