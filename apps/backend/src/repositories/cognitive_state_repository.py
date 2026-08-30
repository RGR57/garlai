from src.models.cognitive_state import CognitiveState


class CognitiveStateRepository:
    """
    In-memory repository for GARL cognitive states.

    Each conversation receives its own persistent
    CognitiveState instance.

    This allows execution state, pending approvals,
    reasoning state, planner notes, and other cognitive
    metadata to survive across multiple HTTP requests.
    """

    def __init__(self):
        self._states: dict[str, CognitiveState] = {}

    def get(
        self,
        conversation_id: str,
    ) -> CognitiveState | None:

        return self._states.get(
            conversation_id
        )

    def get_or_create(
        self,
        conversation_id: str,
    ) -> CognitiveState:

        state = self.get(
            conversation_id
        )

        if state is None:

            state = CognitiveState()

            self._states[
                conversation_id
            ] = state

        return state

    def save(
        self,
        conversation_id: str,
        state: CognitiveState,
    ) -> None:

        self._states[
            conversation_id
        ] = state

    def delete(
        self,
        conversation_id: str,
    ) -> None:

        self._states.pop(
            conversation_id,
            None,
        )

    def clear(
        self,
    ) -> None:

        self._states.clear()