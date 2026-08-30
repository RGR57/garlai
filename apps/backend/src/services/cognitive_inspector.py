from typing import Any

from src.models.cognitive_state import CognitiveState


class CognitiveInspector:
    """
    Converts GARL's internal cognitive state into a
    structured, developer-friendly representation.

    This service is intended for debugging, telemetry,
    testing, and future evaluation systems.
    """

    def inspect(
        self,
        state: CognitiveState,
    ) -> dict[str, Any]:

        return {
            "objective": state.objective,

            "status": {
                "iteration": state.iteration,
                "max_iterations": state.max_iterations,
                "confidence": state.confidence,
                "final_response": state.final_response,
            },

            "execution": self._execution_state(
                state
            ),

            "reasoning": self._reasoning_state(
                state
            ),

            "planner_notes": list(
                state.planner_notes
            ),

            "reviewer_notes": list(
                state.reviewer_notes
            ),
        }

    def _execution_state(
        self,
        state: CognitiveState,
    ) -> dict[str, Any]:

        execution = state.execution

        return {
            "attempt": getattr(
                execution,
                "attempt",
                0,
            ),

            "current_step": (
                execution.current_step
            ),

            "variables": dict(
                execution.variables
            ),

            "approval": {
                "required": (
                    execution.approval_required
                ),
                "tool": (
                    execution.pending_tool
                ),
                "arguments": (
                    execution.pending_arguments
                ),
                "reason": (
                    execution.approval_reason
                ),
                "risk_level": (
                    execution.risk_level
                ),
                "step_id": (
                    execution.pending_step_id
                ),
            },

            "history": [
                {
                    "step_id": result.step_id,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                }
                for result in execution.history
            ],
        }

    def _reasoning_state(
        self,
        state: CognitiveState,
    ) -> list[dict[str, Any]]:

        return [
            {
                "type": node.type.value,
                "content": node.content,
                "confidence": node.confidence,
                "metadata": dict(
                    node.metadata
                ),
            }
            for node in state.reasoning.nodes
        ]