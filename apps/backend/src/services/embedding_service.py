from abc import ABC, abstractmethod

from src.models.chunk import Chunk

from src.utils.logger import logger


class EmbeddingProvider(ABC):

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        ...


class EmbeddingService:

    def __init__(
        self,
        provider: EmbeddingProvider,
    ):
        self.provider = provider

    async def embed_chunks(
        self,
        chunks: list[Chunk],
    ) -> list[Chunk]:

        if not chunks:
            return []

        logger.info(
            f"Generating embeddings for "
            f"{len(chunks)} chunks."
        )

        vectors = await self.provider.embed(
            [
                chunk.content
                for chunk in chunks
            ]
        )

        if len(vectors) != len(chunks):

            raise RuntimeError(
                "Embedding provider returned "
                "an invalid number of vectors."
            )
        for chunk, vector in zip(
            chunks,
            vectors,
        ):

            chunk.set_embedding(
                vector
            )

        logger.info(
            "Embeddings generated successfully."
        )

        return chunks

    async def embed_chunk(
        self,
        chunk: Chunk,
    ) -> Chunk:

        embedded = await self.embed_chunks(
            [chunk]
        )

        return embedded[0]

    async def embed_text(
        self,
        text: str,
    ) -> list[float]:

        vectors = await self.provider.embed(
            [text]
        )

        return vectors[0]
    async def embed_documents(
        self,
        documents: list[str],
    ) -> list[list[float]]:

        if not documents:
            return []

        logger.info(
            f"Embedding "
            f"{len(documents)} documents."
        )

        return await self.provider.embed(
            documents
        )

    async def embed_document(
        self,
        document: str,
    ) -> list[float]:

        return await self.embed_text(
            document
        )

    async def health_check(
        self,
    ) -> bool:

        try:

            await self.embed_text(
                "health check"
            )

            return True

        except Exception:

            return False
    async def embed_query(
        self,
        query: str,
    ) -> list[float]:

        logger.info(
            "Embedding search query."
        )

        return await self.embed_text(
            query
        )

    async def embed_batch(
        self,
        texts: list[str],
    ) -> list[list[float]]:

        if not texts:
            return []

        logger.info(
            f"Embedding batch of "
            f"{len(texts)} texts."
        )

        return await self.provider.embed(
            texts
        )

    @property
    def provider_name(
        self,
    ) -> str:

        return (
            self.provider.__class__.__name__
        )
    async def dimension(
        self,
    ) -> int:

        vector = await self.embed_text(
            "dimension check"
        )

        return len(
            vector
        )

    def __repr__(
        self,
    ) -> str:

        return (
            "EmbeddingService("
            f"provider={self.provider_name})"
        )