from abc import ABC, abstractmethod

from src.models.conversation import ConversationMessage


class ConversationRepository(ABC):
    """
    Abstract repository for conversation storage.
    """

    @abstractmethod
    async def add_message(
        self,
        conversation_id: str,
        message: ConversationMessage,
    ) -> None:
        """
        Store a single message.
        """
        pass

    @abstractmethod
    async def get_messages(
        self,
        conversation_id: str,
    ) -> list[ConversationMessage]:
        """
        Retrieve all messages for a conversation.
        """
        pass