from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class Chunk:

    id: str = field(
        default_factory=lambda: str(
            uuid4()
        )
    )

    document_id: str = ""

    index: int = 0

    content: str = ""

    embedding: list[float] = field(
        default_factory=list
    )

    metadata: dict[str, object] = field(
        default_factory=dict
    )

    created_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    @property
    def token_count(
        self,
    ) -> int:

        return len(
            self.content.split()
        )

    @property
    def character_count(
        self,
    ) -> int:

        return len(
            self.content
        )
    @property
    def is_embedded(
        self,
    ) -> bool:

        return len(
            self.embedding
        ) > 0

    def set_embedding(
        self,
        embedding: list[float],
    ) -> None:

        self.embedding = embedding

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

    def clear_embedding(
        self,
    ) -> None:

        self.embedding.clear()
    def to_dict(
        self,
    ) -> dict:

        return {
            "id": self.id,
            "document_id": self.document_id,
            "index": self.index,
            "content": self.content,
            "embedding": self.embedding,
            "metadata": self.metadata,
            "created_at": (
                self.created_at.isoformat()
            ),
        }

    def __len__(
        self,
    ) -> int:

        return len(
            self.content
        )

    def __bool__(
        self,
    ) -> bool:

        return bool(
            self.content
        )