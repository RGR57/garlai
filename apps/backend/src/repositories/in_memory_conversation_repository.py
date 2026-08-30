from collections import defaultdict

from src.models.conversation import ConversationMessage
from src.repositories.conversation_repository import ConversationRepository


class InMemoryConversationRepository(ConversationRepository):
    """
    Temporary repository used during development.
    Will later be replaced by PostgreSQL without
    changing the ConversationService.
    """

    def __init__(self):
        self._storage = defaultdict(list)

    async def add_message(
        self,
        conversation_id: str,
        message: ConversationMessage,
    ) -> None:

        self._storage[conversation_id].append(message)

    async def get_messages(
        self,
        conversation_id: str,
    ) -> list[ConversationMessage]:

        return self._storage[conversation_id]