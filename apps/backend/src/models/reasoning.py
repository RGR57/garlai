from dataclasses import dataclass, field
from enum import Enum


class ReasoningType(str, Enum):

    OBJECTIVE = "objective"

    CONSTRAINT = "constraint"

    ASSUMPTION = "assumption"

    STRATEGY = "strategy"

    OBSERVATION = "observation"

    REFLECTION = "reflection"


@dataclass
class ReasoningNode:

    thought: str

    reasoning_type: ReasoningType

    confidence: float = 1.0


@dataclass
class ReasoningChain:

    nodes: list[ReasoningNode] = field(
        default_factory=list
    )

    def add(
        self,
        thought: str,
        reasoning_type: ReasoningType,
        confidence: float = 1.0,
    ):

        self.nodes.append(
            ReasoningNode(
                thought=thought,
                reasoning_type=reasoning_type,
                confidence=confidence,
            )
        )

    def thoughts(
        self,
    ) -> list[str]:

        return [
            node.thought
            for node in self.nodes
        ]