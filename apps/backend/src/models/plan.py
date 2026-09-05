from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanStep:
    id: int
    action: str

    # Human-readable / LLM step input.
    # Kept for backward compatibility.
    input: str = ""

    # Tool selected by the planner.
    # None means this is an LLM-only step.
    tool: str | None = None

    # Structured arguments passed directly to the tool.
    arguments: dict[str, Any] = field(
        default_factory=dict
    )

    # Optional constrained JSON output for a tool-free LLM step.
    result_contract: str | None = None


@dataclass
class ExecutionPlan:
    steps: list[PlanStep] = field(
        default_factory=list
    )

    def add_step(
        self,
        step: PlanStep,
    ) -> None:
        self.steps.append(step)

    @property
    def is_empty(self) -> bool:
        return len(self.steps) == 0
