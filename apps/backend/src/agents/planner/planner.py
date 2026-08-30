from .schemas import Plan, Task


class Planner:
    """
    Planner Agent.

    Converts a high-level objective into
    an ordered execution plan.
    """

    async def plan(self, objective: str) -> Plan:

        tasks = [
            Task(
                id=1,
                title="Analyze Objective",
                description="Understand the requested objective."
            ),
            Task(
                id=2,
                title="Create Project Structure",
                description="Generate the initial folder structure.",
                dependencies=[1]
            ),
            Task(
                id=3,
                title="Generate Implementation Plan",
                description="Prepare execution roadmap.",
                dependencies=[2]
            )
        ]

        return Plan(
            objective=objective,
            tasks=tasks
        )