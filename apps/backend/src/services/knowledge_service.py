from src.models.document import Document
from src.models.retrieval_result import (
    RetrievalResult,
)

from src.services.document_loader import (
    DocumentLoader,
)
from src.services.retrieval_service import (
    RetrievalService,
)

from src.utils.logger import logger


class KnowledgeService:

    def __init__(
        self,
        loader: DocumentLoader,
        retrieval: RetrievalService,
    ):
        self.loader = loader
        self.retrieval = retrieval

    async def ingest_document(
        self,
        path: str,
    ) -> int:

        logger.info(
            f"Ingesting document: {path}"
        )

        document = self.loader.load(
            path
        )

        return await self.retrieval.index_document(
            document
        )

    async def ingest_documents(
        self,
        paths: list[str],
    ) -> int:

        documents = [
            self.loader.load(path)
            for path in paths
        ]

        return await self.retrieval.index_documents(
            documents
        )
    async def ingest_directory(
        self,
        directory: str,
        recursive: bool = True,
    ) -> int:

        documents = (
            self.loader.load_directory(
                directory,
                recursive=recursive,
            )
        )

        return await self.retrieval.index_documents(
            documents
        )

    async def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[RetrievalResult]:

        logger.info(
            f"Knowledge search: {query}"
        )

        return await self.retrieval.search(
            query,
            limit,
        )

    async def search_context(
        self,
        query: str,
        limit: int = 5,
    ) -> str:

        return await self.retrieval.search_context(
            query,
            limit,
        )
    async def search_chunks(
        self,
        query: str,
        limit: int = 5,
    ):

        return await self.retrieval.search_chunks(
            query,
            limit,
        )

    async def get_document(
        self,
        path: str,
    ) -> Document:

        return self.loader.load(
            path
        )

    async def get_documents(
        self,
        directory: str,
    ) -> list[Document]:

        return self.loader.load_directory(
            directory
        )

    async def indexed_chunks(
        self,
    ) -> int:

        return await self.retrieval.indexed_chunks()
    async def clear(
        self,
    ) -> None:

        await self.retrieval.clear()

    async def health_check(
        self,
    ) -> bool:

        return await self.retrieval.health_check()

    async def remove_document(
        self,
        document_id: str,
    ) -> None:

        await self.retrieval.remove_document(
            document_id
        )

    async def all_chunks(
        self,
    ):

        return await self.retrieval.all_chunks()
    async def statistics(
        self,
    ) -> dict[str, int]:

        return {
            "indexed_chunks": (
                await self.indexed_chunks()
            )
        }

    def __repr__(
        self,
    ) -> str:

        return (
            "KnowledgeService("
            f"loader={self.loader.__class__.__name__}, "
            f"retrieval={self.retrieval.__class__.__name__})"
        )