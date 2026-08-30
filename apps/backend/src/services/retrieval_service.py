from src.models.chunk import Chunk
from src.models.document import Document
from src.models.retrieval_result import (
    RetrievalResult,
)

from src.services.chunker import Chunker
from src.services.embedding_service import (
    EmbeddingService,
)
from src.services.vector_store import (
    VectorStore,
)

from src.utils.logger import logger


class RetrievalService:

    def __init__(
        self,
        chunker: Chunker,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
    ):
        self.chunker = chunker
        self.embedding_service = (
            embedding_service
        )
        self.vector_store = (
            vector_store
        )

    async def index_document(
        self,
        document: Document,
    ) -> int:

        logger.info(
            f"Indexing document: "
            f"{document.name}"
        )

        chunks = self.chunker.chunk(
            document
        )

        chunks = (
            await self.embedding_service
            .embed_chunks(chunks)
        )

        await self.vector_store.add(
            chunks
        )

        return len(chunks)
    async def index_documents(
        self,
        documents: list[Document],
    ) -> int:

        total = 0

        for document in documents:

            total += await self.index_document(
                document
            )

        logger.info(
            f"Indexed {total} chunks."
        )

        return total

    async def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[RetrievalResult]:

        logger.info(
            f"Searching: {query}"
        )

        embedding = (
            await self.embedding_service
            .embed_query(query)
        )

        return await self.vector_store.search(
            embedding,
            limit,
        )
    async def search_chunks(
        self,
        query: str,
        limit: int = 5,
    ) -> list[Chunk]:

        results = await self.search(
            query,
            limit,
        )

        return [
            result.chunk
            for result in results
        ]

    async def search_context(
        self,
        query: str,
        limit: int = 5,
    ) -> str:

        results = await self.search(
            query,
            limit,
        )

        if not results:
            return ""

        return "\n\n".join(
            result.content
            for result in results
        )
    async def remove_document(
        self,
        document_id: str,
    ) -> None:

        await self.vector_store.remove_document(
            document_id
        )

    async def clear(
        self,
    ) -> None:

        await self.vector_store.clear()

    async def indexed_chunks(
        self,
    ) -> int:

        return await self.vector_store.count()

    async def health_check(
        self,
    ) -> bool:

        return (
            await self.embedding_service
            .health_check()
        )
    async def all_chunks(
        self,
    ) -> list[Chunk]:

        return await self.vector_store.all_chunks()

    def __repr__(
        self,
    ) -> str:

        return (
            "RetrievalService("
            f"chunk_size="
            f"{self.chunker.chunk_size}, "
            f"provider="
            f"{self.embedding_service.provider_name})"
        )