from dataclasses import dataclass, field

from src.models.execution_state import ExecutionState
from src.models.execution_trace import ExecutionTrace
from src.models.reasoning import ReasoningChain

from src.models.artifact import Artifact
@dataclass
class CognitiveState:

    # ======================================================
    # USER OBJECTIVE
    # ======================================================

    objective: str = ""

    # ======================================================
    # COGNITIVE REASONING
    # ======================================================

    reasoning: ReasoningChain = field(
        default_factory=ReasoningChain
    )

    # ======================================================
    # EXECUTION HISTORY
    # ======================================================

    execution_trace: ExecutionTrace = field(
        default_factory=ExecutionTrace
    )

    # ======================================================
    # EXECUTION STATE
    # ======================================================

    execution: ExecutionState = field(
        default_factory=ExecutionState
    )

    # ======================================================
    # MEMORY
    # ======================================================

    memories: list[str] = field(
        default_factory=list
    )
    knowledge_context: str = ""

    retrieved_documents: list[str] = field(
        default_factory=list
    )

    # ======================================================
    # COGNITIVE NOTES
    # ======================================================

    planner_notes: list[str] = field(
        default_factory=list
    )

    reviewer_notes: list[str] = field(
        default_factory=list
    )

    # ======================================================
    # EXECUTION METADATA
    # ======================================================

    confidence: float = 1.0

    iteration: int = 0

    max_iterations: int = 5
    artifacts: list[Artifact] = field(
    default_factory=list
)

    final_response: str = ""
