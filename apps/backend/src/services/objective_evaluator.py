from dataclasses import dataclass
import re
from typing import Any

from src.models.artifact import Artifact
from src.models.durable_execution import ApprovalEvidence, OperationEvidence
from src.models.execution_state import ExecutionState


@dataclass(frozen=True)
class ObjectiveEvaluation:
    complete: bool
    summary: str
    gaps: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]
    verification: tuple[str, ...]


@dataclass(frozen=True)
class ExternalConfirmationEvidence:
    """A bounded, persisted observation that confirms an external operation."""

    execution_id: str
    step_id: int
    operation_id: str
    payload_hash: str
    observation_id: str
    confirmation_hash: str


@dataclass(frozen=True)
class ObjectiveEvaluationContext:
    """Repository-independent durable facts supplied by the active runtime."""

    approvals: tuple[ApprovalEvidence, ...] = ()
    operations: tuple[OperationEvidence, ...] = ()
    confirmations: tuple[ExternalConfirmationEvidence, ...] = ()


class ObjectiveEvaluator:
    """Deterministically evaluate observable benchmark requirements."""

    def evaluate(
        self,
        objective: str,
        execution_state: ExecutionState,
        artifacts: list[Artifact],
        context: ObjectiveEvaluationContext | None = None,
    ) -> ObjectiveEvaluation:
        objective_terms = objective.lower()
        gaps: list[str] = []
        evidence = self._research_evidence(execution_state)
        verification = self._verification(execution_state)
        needs_research = any(term in objective_terms for term in ("research", "evidence"))
        needs_prototype = any(term in objective_terms for term in ("prototype", "build", "software"))
        needs_verification = any(term in objective_terms for term in ("verify", "working"))

        if needs_research and not evidence:
            gaps.append("No valid research evidence was observed.")
        if needs_prototype and not (artifacts or self._successful_tool(execution_state, "filesystem")):
            gaps.append("No prototype artifact was observed.")
        failed_verifications = [result.error for result in execution_state.history if result.tool == "terminal" and not result.success]
        if needs_verification and failed_verifications:
            gaps.extend(f"Verification failed: {error}" for error in failed_verifications)
        elif needs_verification and not verification:
            gaps.append("No successful verification was observed.")

        if self._needs_browser_commitment(objective_terms):
            gaps.extend(
                self._browser_commitment_gaps(
                    objective,
                    execution_state,
                    context or ObjectiveEvaluationContext(),
                )
            )

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

    @staticmethod
    def _needs_browser_commitment(objective_terms: str) -> bool:
        return (
            "marketplace" in objective_terms
            and "signup" in objective_terms
            and "final commitment" in objective_terms
        )

    def _browser_commitment_gaps(
        self,
        objective: str,
        state: ExecutionState,
        context: ObjectiveEvaluationContext,
    ) -> list[str]:
        gaps = self._browser_selection_gaps(objective, state)
        if not self._successful_tool(state, "browser_fill"):
            gaps.append("No prepared signup details were observed.")

        approved = [
            item for item in context.approvals if item.event_type == "approved"
        ]
        rejected = [
            item for item in context.approvals if item.event_type == "rejected"
        ]
        if not approved:
            gaps.append(
                "The final commitment approval was rejected."
                if rejected
                else "No durable approval granted for the final commitment."
            )
            return gaps

        completed = [
            operation
            for operation in context.operations
            if operation.event_type == "completed"
            and any(
                approval.execution_id == operation.execution_id
                and approval.step_id == operation.step_id
                and approval.operation_id == operation.operation_id
                and approval.payload_hash == operation.payload_hash
                for approval in approved
            )
        ]
        if len(completed) != 1:
            gaps.append("No completed durable final commitment operation was observed.")
            return gaps

        operation = completed[0]
        confirmed = any(
            confirmation.execution_id == operation.execution_id
            and confirmation.step_id == operation.step_id
            and confirmation.operation_id == operation.operation_id
            and confirmation.payload_hash == operation.payload_hash
            and confirmation.observation_id
            and confirmation.confirmation_hash
            for confirmation in context.confirmations
        )
        if not confirmed:
            gaps.append("No persisted external success confirmation was observed.")
        return gaps

    def _browser_selection_gaps(
        self,
        objective: str,
        state: ExecutionState,
    ) -> list[str]:
        observations = self._observed_browser_elements(state)
        selected = self._selected_browser_plan(state)
        if selected is None:
            return ["No observed marketplace plan was selected."]

        observation_id, target = selected
        candidates = observations.get(observation_id, {})
        element = candidates.get(target.get("element_ref"))
        if (
            not isinstance(element, dict)
            or element.get("semantic_fingerprint") != target.get("semantic_fingerprint")
            or element.get("accessible_name") != target.get("accessible_name")
        ):
            return ["Selected marketplace plan is not linked to an observed element."]

        minimum_users = self._minimum_users(objective)
        qualifying = [
            facts
            for facts in (self._plan_facts(item) for item in candidates.values())
            if facts is not None and facts["sso"] and facts["users"] >= minimum_users
        ]
        selected_facts = self._plan_facts(element)
        if selected_facts is None or not selected_facts["sso"] or selected_facts["users"] < minimum_users:
            return ["Selected plan does not satisfy the observed SSO and user requirements."]
        if not qualifying:
            return ["No observed marketplace plan satisfies the requested constraints."]
        lowest_price = min(facts["price"] for facts in qualifying)
        if selected_facts["price"] != lowest_price:
            return ["Selected plan is not the cheapest qualifying observed plan."]
        return []

    @staticmethod
    def _observed_browser_elements(
        state: ExecutionState,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        observations: dict[str, dict[str, dict[str, Any]]] = {}
        for result in state.history:
            if not result.success or result.tool != "browser_observe" or not isinstance(result.output, dict):
                continue
            observation = result.output.get("observation")
            if not isinstance(observation, dict):
                continue
            observation_id = observation.get("observation_id")
            elements = observation.get("elements")
            if not isinstance(observation_id, str) or not isinstance(elements, list):
                continue
            observations[observation_id] = {
                item["element_ref"]: item
                for item in elements
                if isinstance(item, dict)
                and isinstance(item.get("element_ref"), str)
                and isinstance(item.get("accessible_name"), str)
            }
        return observations

    @staticmethod
    def _selected_browser_plan(
        state: ExecutionState,
    ) -> tuple[str, dict[str, Any]] | None:
        for result in reversed(state.history):
            if not result.success or result.tool != "browser_select" or not isinstance(result.output, dict):
                continue
            receipt = result.output.get("receipt")
            target = receipt.get("target") if isinstance(receipt, dict) else None
            if not isinstance(target, dict):
                continue
            observation_id = target.get("observation_id")
            if isinstance(observation_id, str):
                return observation_id, target
        return None

    @staticmethod
    def _minimum_users(objective: str) -> int:
        match = re.search(r"at least\s+(\d+)\s+users", objective, re.IGNORECASE)
        return int(match.group(1)) if match else 1

    @staticmethod
    def _plan_facts(element: dict[str, Any]) -> dict[str, Any] | None:
        name = element.get("accessible_name")
        text = element.get("text_context")
        if not isinstance(name, str) or not name.startswith("Choose ") or not isinstance(text, str):
            return None
        price = re.search(r"\$(\d+(?:\.\d+)?)", text)
        users = re.search(r"users?\s*:\s*(\d+)|(\d+)\s+users?", text, re.IGNORECASE)
        if price is None or users is None:
            return None
        user_count = users.group(1) or users.group(2)
        return {
            "name": name.removeprefix("Choose ").strip(),
            "price": float(price.group(1)),
            "users": int(user_count),
            "sso": bool(re.search(r"(?:sso\s*:\s*yes|supports\s+sso)", text, re.IGNORECASE)),
        }
