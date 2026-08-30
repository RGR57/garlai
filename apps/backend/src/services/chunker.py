from src.models.chunk import Chunk
from src.models.document import Document

from src.utils.logger import logger


class Chunker:

    DEFAULT_CHUNK_SIZE = 1000

    DEFAULT_OVERLAP = 200

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ):

        if overlap >= chunk_size:

            raise ValueError(
                "Overlap must be smaller "
                "than chunk size."
            )

        self.chunk_size = chunk_size

        self.overlap = overlap

    def chunk(
        self,
        document: Document,
    ) -> list[Chunk]:

        logger.info(
            f"Chunking document: "
            f"{document.name}"
        )

        if not document.content.strip():

            return []

        chunks: list[Chunk] = []

        text = document.content

        start = 0

        index = 0
        while start < len(text):

            end = min(
                start + self.chunk_size,
                len(text),
            )

            chunk_text = text[
                start:end
            ].strip()

            if chunk_text:

                chunks.append(
                    Chunk(
                        document_id=document.id,
                        index=index,
                        content=chunk_text,
                        metadata={
                            "start": start,
                            "end": end,
                            "document": document.name,
                        },
                    )
                )

                index += 1

            if end >= len(text):
                break

            start = (
                end - self.overlap
            )

        logger.info(
            f"Created "
            f"{len(chunks)} chunks."
        )

        return chunks
    def chunk_many(
        self,
        documents: list[Document],
    ) -> list[Chunk]:

        chunks: list[Chunk] = []

        for document in documents:

            chunks.extend(
                self.chunk(
                    document
                )
            )

        return chunks

    def estimate_chunks(
        self,
        document: Document,
    ) -> int:

        if not document.content:

            return 0

        step = (
            self.chunk_size
            - self.overlap
        )

        return max(
            1,
            (
                len(document.content)
                + step
                - 1
            )
            // step,
        )
    def set_chunk_size(
        self,
        chunk_size: int,
    ) -> None:

        if chunk_size <= 0:

            raise ValueError(
                "Chunk size must be greater than zero."
            )

        if self.overlap >= chunk_size:

            raise ValueError(
                "Chunk size must be larger than overlap."
            )

        self.chunk_size = chunk_size

    def set_overlap(
        self,
        overlap: int,
    ) -> None:

        if overlap < 0:

            raise ValueError(
                "Overlap cannot be negative."
            )

        if overlap >= self.chunk_size:

            raise ValueError(
                "Overlap must be smaller than chunk size."
            )

        self.overlap = overlap

    def configuration(
        self,
    ) -> dict[str, int]:

        return {
            "chunk_size": self.chunk_size,
            "overlap": self.overlap,
        }
    def __call__(
        self,
        document: Document,
    ) -> list[Chunk]:

        return self.chunk(
            document
        )

    def __repr__(
        self,
    ) -> str:

        return (
            "Chunker("
            f"chunk_size={self.chunk_size}, "
            f"overlap={self.overlap})"
        )