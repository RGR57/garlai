from dataclasses import dataclass, field

from src.models.chunk import Chunk


@dataclass
class RetrievalResult:

    chunk: Chunk

    score: float

    document_name: str = ""

    source: str = ""

    metadata: dict[str, object] = field(
        default_factory=dict
    )

    @property
    def content(
        self,
    ) -> str:

        return self.chunk.content

    @property
    def document_id(
        self,
    ) -> str:

        return self.chunk.document_id

    @property
    def chunk_id(
        self,
    ) -> str:

        return self.chunk.id
    @property
    def has_metadata(
        self,
    ) -> bool:

        return bool(
            self.metadata
        )

    def add_metadata(
        self,
        key: str,
        value: object,
    ) -> None:

        self.metadata[key] = value

    def remove_metadata(
        self,
        key: str,
    ) -> None:

        self.metadata.pop(
            key,
            None,
        )

    def update_score(
        self,
        score: float,
    ) -> None:

        self.score = score
    def to_dict(
        self,
    ) -> dict:

        return {
            "chunk_id": self.chunk.id,
            "document_id": self.chunk.document_id,
            "document_name": self.document_name,
            "content": self.chunk.content,
            "score": self.score,
            "source": self.source,
            "metadata": self.metadata,
        }

    def __lt__(
        self,
        other: "RetrievalResult",
    ) -> bool:

        return self.score < other.score

    def __repr__(
        self,
    ) -> str:

        return (
            "RetrievalResult("
            f"score={self.score:.4f}, "
            f"document='{self.document_name}', "
            f"chunk='{self.chunk.id}')"
        )