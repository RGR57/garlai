from typing import Any
import re

from src.models.execution_state import ExecutionState


class VariableResolver:

    _EXACT_REFERENCE = re.compile(r"^\{\{([^{}]+)\}\}$")

    def resolve(
        self,
        value: Any,
        state: ExecutionState,
    ) -> Any:
        """
        Recursively resolve execution variables such as:

        {{step1}}
        {{step2}}

        inside strings, dictionaries, lists, and tuples.
        """

        if isinstance(value, str):
            return self._resolve_string(
                value,
                state,
            )

        if isinstance(value, dict):
            return {
                key: self.resolve(
                    item,
                    state,
                )
                for key, item in value.items()
            }

        if isinstance(value, list):
            return [
                self.resolve(
                    item,
                    state,
                )
                for item in value
            ]

        if isinstance(value, tuple):
            return tuple(
                self.resolve(
                    item,
                    state,
                )
                for item in value
            )

        return value

    def _resolve_string(
        self,
        text: str,
        state: ExecutionState,
    ) -> Any:

        exact_reference = self._EXACT_REFERENCE.fullmatch(text)
        if exact_reference is not None:
            key = exact_reference.group(1)
            if key in state.variables:
                return state.variables[key]

        result = text

        for key, value in state.variables.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder not in result:
                continue
            if not isinstance(value, (str, int, float, bool, type(None))):
                value = self._embedded_research_text(key, value, state)
            result = result.replace(placeholder, str(value))

        return result

    @staticmethod
    def _embedded_research_text(
        key: str,
        value: Any,
        state: ExecutionState,
    ) -> str:
        if not key.startswith("step") or not key[4:].isdigit() or not isinstance(value, dict):
            raise ValueError(f"Structured variable '{key}' cannot be embedded in text.")
        step_id = int(key[4:])
        result = next((item for item in state.history if item.step_id == step_id), None)
        if (
            result is None
            or result.tool != "web_search"
            or value.get("trust") != "untrusted_external_evidence"
            or not isinstance(value.get("evidence"), list)
        ):
            raise ValueError(f"Structured variable '{key}' cannot be embedded in text.")
        snippets = [
            item.get("snippet")
            for item in value["evidence"]
            if isinstance(item, dict) and isinstance(item.get("snippet"), str)
        ]
        if not snippets:
            raise ValueError(f"Structured variable '{key}' has no renderable research evidence.")
        return "\n".join(snippets)
