from .planner import Planner
from .schemas import Plan


class PlannerService:

    def __init__(self):
        self.planner = Planner()

    async def create_plan(self, objective: str) -> Plan:
        return await self.planner.plan(objective)