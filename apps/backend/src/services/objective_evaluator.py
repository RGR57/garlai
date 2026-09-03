from dataclasses import dataclass
from typing import Any

from src.models.artifact import Artifact
from src.models.execution_state import ExecutionState


@dataclass(frozen=True)
class ObjectiveEvaluation:
    complete: bool
    summary: str
    gaps: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]
    verification: tuple[str, ...]


class ObjectiveEvaluator:
    """Deterministically evaluate observable benchmark requirements."""

    def evaluate(
        self,
        objective: str,
        execution_state: ExecutionState,
        artifacts: list[Artifact],
    ) -> ObjectiveEvaluation:
        objective_terms = objective.lower()
        gaps: list[str] = []
        evidence = self._research_evidence(execution_state)
        verification = self._verification(execution_state)
        needs_research = any(term in objective_terms for term in ("research", "market", "evidence"))
        needs_prototype = any(term in objective_terms for term in ("prototype", "build", "software"))
        needs_verification = any(term in objective_terms for term in ("verify", "test", "working"))

        if needs_research and not evidence:
            gaps.append("No valid research evidence was observed.")
        if needs_prototype and not (artifacts or self._successful_tool(execution_state, "filesystem")):
            gaps.append("No prototype artifact was observed.")
        failed_verifications = [result.error for result in execution_state.history if result.tool == "terminal" and not result.success]
        if needs_verification and failed_verifications:
            gaps.extend(f"Verification failed: {error}" for error in failed_verifications)
        elif needs_verification and not verification:
            gaps.append("No successful verification was observed.")

        complete = not gaps
        return ObjectiveEvaluation(
            complete=complete,
            summary="Objective requirements observed." if complete else "Objective requirements remain incomplete.",
            gaps=tuple(gaps),
            evidence=tuple(evidence),
            verification=tuple(verification),
        )

    @staticmethod
    def _successful_tool(state: ExecutionState, tool_name: str) -> bool:
        return any(result.success and result.tool == tool_name for result in state.history)

    @staticmethod
    def _research_evidence(state: ExecutionState) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for result in state.history:
            if not result.success or result.tool != "web_search" or not isinstance(result.output, dict):
                continue
            output_evidence = result.output.get("evidence")
            if isinstance(output_evidence, list):
                evidence.extend(item for item in output_evidence if isinstance(item, dict) and item.get("url"))
        return evidence

    @staticmethod
    def _verification(state: ExecutionState) -> list[str]:
        return [
            str(result.output)
            for result in state.history
            if result.success
            and result.output is not None
            and (
                result.tool == "terminal"
                or "verify" in (result.action or "").lower()
            )
        ]
