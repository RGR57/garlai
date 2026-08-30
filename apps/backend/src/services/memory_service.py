import re
from datetime import datetime, timezone
from uuid import uuid4

from src.models.memory import (
    Memory,
    MemoryType,
)
from src.repositories.memory_repository import (
    MemoryRepository,
)


class MemoryService:

    def __init__(
        self,
        repository: MemoryRepository,
    ):
        self.repository = repository

    # ==========================================================
    # STORE
    # ==========================================================

    async def store(
        self,
        conversation_id: str,
        content: str,
        *,
        memory_type: MemoryType = MemoryType.CONTEXT,
        importance: float = 0.5,
    ) -> Memory:

        content = content.strip()

        if not content:
            raise ValueError(
                "Memory content cannot be empty."
            )

        importance = max(
            0.0,
            min(
                1.0,
                importance,
            ),
        )

        existing_memories = (
            await self.repository.get_memories(
                conversation_id
            )
        )

        normalized_content = (
            self._normalize(content)
        )

        # ------------------------------------------------------
        # DEDUPLICATION
        # ------------------------------------------------------

        for memory in existing_memories:

            if (
                self._normalize(
                    memory.content
                )
                == normalized_content
            ):

                # Preserve the highest importance
                # if the same memory is stored again.

                memory.importance = max(
                    memory.importance,
                    importance,
                )

                return memory

        memory = Memory(
            id=str(uuid4()),
            content=content,
            created_at=datetime.now(
                timezone.utc
            ),
            memory_type=memory_type,
            importance=importance,
        )

        await self.repository.add_memory(
            conversation_id,
            memory,
        )

        return memory

    # ==========================================================
    # RETRIEVE ALL
    # ==========================================================

    async def retrieve(
        self,
        conversation_id: str,
    ) -> list[Memory]:

        return (
            await self.repository.get_memories(
                conversation_id
            )
        )

    # ==========================================================
    # RETRIEVE RELEVANT
    # ==========================================================

    async def retrieve_relevant(
        self,
        conversation_id: str,
        query: str,
        *,
        limit: int = 5,
    ) -> list[Memory]:

        memories = (
            await self.repository.get_memories(
                conversation_id
            )
        )

        if not memories:
            return []

        query_tokens = self._tokenize(
            query
        )

        scored_memories: list[
            tuple[float, Memory]
        ] = []

        for memory in memories:

            score = self._score_memory(
                memory,
                query_tokens,
            )

            if score > 0:

                scored_memories.append(
                    (
                        score,
                        memory,
                    )
                )

        scored_memories.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        selected = [
            memory
            for _, memory
            in scored_memories[:limit]
        ]

        for memory in selected:
            memory.touch()

        return selected

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete(
        self,
        conversation_id: str,
        memory_id: str,
    ) -> bool:

        return (
            await self.repository.delete_memory(
                conversation_id,
                memory_id,
            )
        )

    # ==========================================================
    # CLEAR
    # ==========================================================

    async def clear(
        self,
        conversation_id: str,
    ) -> None:

        await self.repository.clear_memories(
            conversation_id
        )

    # ==========================================================
    # SCORING
    # ==========================================================

    def _score_memory(
        self,
        memory: Memory,
        query_tokens: set[str],
    ) -> float:

        memory_tokens = self._tokenize(
            memory.content
        )

        if not memory_tokens:
            return 0.0

        # ------------------------------------------------------
        # KEYWORD RELEVANCE
        # ------------------------------------------------------

        overlap = (
            query_tokens
            & memory_tokens
        )

        relevance = (
            len(overlap)
            / max(
                len(query_tokens),
                1,
            )
        )

        # ------------------------------------------------------
        # IMPORTANCE
        # ------------------------------------------------------

        importance_score = (
            memory.importance
        )

        # ------------------------------------------------------
        # ACCESS FREQUENCY
        # ------------------------------------------------------

        access_score = min(
            memory.access_count / 10,
            1.0,
        )

        # ------------------------------------------------------
        # FINAL SCORE
        # ------------------------------------------------------

        return (
            relevance * 0.70
            + importance_score * 0.25
            + access_score * 0.05
        )

    # ==========================================================
    # TOKENIZATION
    # ==========================================================

    def _tokenize(
        self,
        text: str,
    ) -> set[str]:

        return set(
            re.findall(
                r"[a-zA-Z0-9_]+",
                text.lower(),
            )
        )

    def _normalize(
        self,
        text: str,
    ) -> str:

        return " ".join(
            text.lower().split()
        )