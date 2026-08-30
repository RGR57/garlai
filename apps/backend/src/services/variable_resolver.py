from typing import Any

from src.models.execution_state import ExecutionState


class VariableResolver:

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
    ) -> str:

        result = text

        for key, value in state.variables.items():

            result = result.replace(
                f"{{{{{key}}}}}",
                str(value),
            )

        return result