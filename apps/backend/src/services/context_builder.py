from src.models.conversation import ConversationMessage
from src.core.config import settings

class ContextBuilder:
    """
    Builds the chat messages sent to the LLM.

    Future versions will include:
    - Memory
    - RAG
    - Tool results
    - Summaries
    """

    async def build(
        self,
        system_prompt: str,
        messages: list[ConversationMessage],
    ) -> list[dict]:

        chat_messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        recent_messages = messages[-settings.MAX_CONTEXT_MESSAGES:]

        for message in recent_messages:
            chat_messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

        return chat_messages