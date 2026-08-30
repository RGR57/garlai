from abc import ABC, abstractmethod
from math import sqrt

from src.models.chunk import Chunk
from src.models.retrieval_result import RetrievalResult

from src.utils.logger import logger


class VectorStoreProvider(ABC):

    @abstractmethod
    async def add(
        self,
        chunks: list[Chunk],
    ) -> None:
        ...

    @abstractmethod
    async def search(
        self,
        embedding: list[float],
        limit: int,
    ) -> list[RetrievalResult]:
        ...

    @abstractmethod
    async def clear(
        self,
    ) -> None:
        ...


class InMemoryVectorStore(
    VectorStoreProvider,
):

    def __init__(
        self,
    ):
        self._chunks: list[Chunk] = []

    async def add(
        self,
        chunks: list[Chunk],
    ) -> None:

        logger.info(
            f"Indexing {len(chunks)} chunks."
        )

        self._chunks.extend(
            chunks
        )
    async def search(
        self,
        embedding: list[float],
        limit: int = 5,
    ) -> list[RetrievalResult]:

        results: list[
            RetrievalResult
        ] = []

        for chunk in self._chunks:

            if not chunk.embedding:
                continue

            score = self._cosine_similarity(
                embedding,
                chunk.embedding,
            )

            results.append(
                RetrievalResult(
                    chunk=chunk,
                    score=score,
                )
            )

        results.sort(
            reverse=True,
        )

        return results[:limit]

    async def clear(
        self,
    ) -> None:

        logger.info(
            "Clearing vector store."
        )

        self._chunks.clear()
    def _cosine_similarity(
        self,
        a: list[float],
        b: list[float],
    ) -> float:

        if len(a) != len(b):
            return 0.0

        dot = sum(
            x * y
            for x, y in zip(a, b)
        )

        norm_a = sqrt(
            sum(
                x * x
                for x in a
            )
        )

        norm_b = sqrt(
            sum(
                y * y
                for y in b
            )
        )

        if (
            norm_a == 0
            or norm_b == 0
        ):
            return 0.0

        return dot / (
            norm_a * norm_b
        )
    async def remove_document(
        self,
        document_id: str,
    ) -> None:

        before = len(
            self._chunks
        )

        self._chunks = [
            chunk
            for chunk in self._chunks
            if chunk.document_id
            != document_id
        ]

        logger.info(
            f"Removed "
            f"{before - len(self._chunks)} "
            f"chunks."
        )

    async def count(
        self,
    ) -> int:

        return len(
            self._chunks
        )

    async def all_chunks(
        self,
    ) -> list[Chunk]:

        return list(
            self._chunks
        )
class VectorStore:

    def __init__(
        self,
        provider: VectorStoreProvider,
    ):
        self.provider = provider

    async def add(
        self,
        chunks: list[Chunk],
    ) -> None:

        await self.provider.add(
            chunks
        )

    async def search(
        self,
        embedding: list[float],
        limit: int = 5,
    ) -> list[RetrievalResult]:

        return await self.provider.search(
            embedding,
            limit,
        )

    async def clear(
        self,
    ) -> None:

        await self.provider.clear()

    async def remove_document(
        self,
        document_id: str,
    ) -> None:

        if hasattr(
            self.provider,
            "remove_document",
        ):

            await self.provider.remove_document(
                document_id
            )
    async def count(
        self,
    ) -> int:

        if hasattr(
            self.provider,
            "count",
        ):

            return await self.provider.count()

        return 0

    async def all_chunks(
        self,
    ) -> list[Chunk]:

        if hasattr(
            self.provider,
            "all_chunks",
        ):

            return await self.provider.all_chunks()

        return []

    def __repr__(
        self,
    ) -> str:

        return (
            "VectorStore("
            f"provider="
            f"{self.provider.__class__.__name__})"
        )