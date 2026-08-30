from abc import ABC, abstractmethod

from src.models.memory import Memory


class MemoryRepository(ABC):

    @abstractmethod
    async def add_memory(
        self,
        conversation_id: str,
        memory: Memory,
    ) -> None:
        ...

    @abstractmethod
    async def get_memories(
        self,
        conversation_id: str,
    ) -> list[Memory]:
        ...

    @abstractmethod
    async def delete_memory(
        self,
        conversation_id: str,
        memory_id: str,
    ) -> bool:
        ...

    @abstractmethod
    async def clear_memories(
        self,
        conversation_id: str,
    ) -> None:
        ...