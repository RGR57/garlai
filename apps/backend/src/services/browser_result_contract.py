import json
from typing import Any

from src.models.browser import BrowserTarget


class BrowserResultContract:
    """Validate the narrow JSON results permitted for browser reasoning steps."""

    @classmethod
    def parse(cls, contract: str, response: str, observation_input: Any) -> dict[str, object]:
        try:
            payload = json.loads(response)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Constrained browser reasoning must return valid JSON.") from exc

        if not isinstance(payload, dict):
            raise ValueError("Constrained browser reasoning must return a JSON object.")

        observation = cls._observation(observation_input)
        elements = observation["elements"]
        if not isinstance(elements, list):
            raise ValueError("Browser observation elements must be a list.")

        if contract == "browser_target":
            return cls._parse_target(payload, observation, elements)
        if contract == "browser_verification":
            return cls._parse_verification(payload, observation, elements)
        raise ValueError(f"Unsupported browser result contract '{contract}'.")

    @staticmethod
    def _observation(observation_input: Any) -> dict[str, Any]:
        if not isinstance(observation_input, dict):
            raise ValueError("Browser result contract requires a browser observation.")
        if observation_input.get("trust") != "untrusted_external_page_data":
            raise ValueError("Browser result contract requires untrusted browser page data.")
        observation = observation_input.get("observation")
        if not isinstance(observation, dict):
            raise ValueError("Browser result contract requires a structured observation.")
        return observation

    @staticmethod
    def _parse_target(
        payload: dict[str, Any],
        observation: dict[str, Any],
        elements: list[Any],
    ) -> dict[str, object]:
        if set(payload) != {"element_ref"} or not isinstance(payload["element_ref"], str):
            raise ValueError("Browser target must contain only a string element_ref.")
        matches = [
            element
            for element in elements
            if isinstance(element, dict) and element.get("element_ref") == payload["element_ref"]
        ]
        if len(matches) != 1:
            raise ValueError("Browser target does not reference an observed element.")
        element = matches[0]
        try:
            target = BrowserTarget(
                browser_session_id=observation["browser_session_id"],
                observation_id=observation["observation_id"],
                element_ref=element["element_ref"],
                observed_url=observation["url"],
                role=element["role"],
                accessible_name=element["accessible_name"],
                label=element.get("label"),
                form_name=element.get("form_name"),
                text_context=element.get("text_context", ""),
                semantic_fingerprint=element["semantic_fingerprint"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Browser observation has an invalid target element.") from exc
        return target.to_payload()

    @staticmethod
    def _parse_verification(
        payload: dict[str, Any],
        observation: dict[str, Any],
        elements: list[Any],
    ) -> dict[str, object]:
        if set(payload) != {"satisfied", "evidence_element_refs"}:
            raise ValueError("Browser verification has an invalid shape.")
        satisfied = payload["satisfied"]
        evidence_refs = payload["evidence_element_refs"]
        if not isinstance(satisfied, bool) or not isinstance(evidence_refs, list):
            raise ValueError("Browser verification has invalid values.")
        if not all(isinstance(reference, str) for reference in evidence_refs):
            raise ValueError("Browser verification evidence references must be strings.")
        observed_refs = {
            element.get("element_ref")
            for element in elements
            if isinstance(element, dict)
        }
        if len(set(evidence_refs)) != len(evidence_refs) or not set(evidence_refs).issubset(observed_refs):
            raise ValueError("Browser verification references an unobserved element.")
        observation_id = observation.get("observation_id")
        if not isinstance(observation_id, str):
            raise ValueError("Browser observation has no observation identity.")
        return {
            "observation_id": observation_id,
            "satisfied": satisfied,
            "evidence_element_refs": evidence_refs,
        }
