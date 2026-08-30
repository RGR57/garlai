from collections import defaultdict

from src.models.memory import Memory
from src.repositories.memory_repository import (
    MemoryRepository,
)


class InMemoryMemoryRepository(
    MemoryRepository
):

    def __init__(self):

        self.memories: dict[
            str,
            list[Memory],
        ] = defaultdict(list)

    async def add_memory(
        self,
        conversation_id: str,
        memory: Memory,
    ) -> None:

        self.memories[
            conversation_id
        ].append(memory)

    async def get_memories(
        self,
        conversation_id: str,
    ) -> list[Memory]:

        return list(
            self.memories.get(
                conversation_id,
                [],
            )
        )

    async def delete_memory(
        self,
        conversation_id: str,
        memory_id: str,
    ) -> bool:

        memories = self.memories.get(
            conversation_id,
            [],
        )

        original_length = len(
            memories
        )

        self.memories[
            conversation_id
        ] = [
            memory
            for memory in memories
            if memory.id != memory_id
        ]

        return (
            len(
                self.memories[
                    conversation_id
                ]
            )
            < original_length
        )

    async def clear_memories(
        self,
        conversation_id: str,
    ) -> None:

        self.memories.pop(
            conversation_id,
            None,
        )