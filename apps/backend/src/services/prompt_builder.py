from typing import Any

from src.models.cognitive_state import CognitiveState
from src.models.conversation import ConversationMessage


class PromptBuilder:

    def build(
        self,
        *,
        system_prompt: str,
        messages: list[ConversationMessage],
        state: CognitiveState,
    ) -> list[dict[str, Any]]:

        prompt: list[dict[str, Any]] = []

        # System prompt
        prompt.append(
            {
                "role": "system",
                "content": system_prompt,
            }
        )

        # Objective
        if state.objective:
            prompt.append(
                {
                    "role": "system",
                    "content": f"Objective: {state.objective}",
                }
            )

        # Memories
        if state.memories:
            prompt.append(
                {
                    "role": "system",
                    "content": "Relevant Memories:\n"
                    + "\n".join(state.memories),
                }
            )

        # Retrieved knowledge
        if state.retrieved_documents:
            prompt.append(
                {
                    "role": "system",
                    "content": "Retrieved Knowledge:\n"
                    + "\n".join(state.retrieved_documents),
                }
            )

        # Conversation history
        for message in messages:
            prompt.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

        return prompt