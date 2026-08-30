from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass
class Document:

    id: str = field(
        default_factory=lambda: str(
            uuid4()
        )
    )

    name: str = ""

    path: str = ""

    content: str = ""

    mime_type: str = ""

    extension: str = ""

    size: int = 0

    source: str = "local"

    created_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    metadata: dict[str, object] = field(
        default_factory=dict
    )

    @classmethod
    def from_file(
        cls,
        path: str,
        content: str,
        mime_type: str = "",
    ) -> "Document":

        p = Path(path)

        return cls(
            name=p.name,
            path=str(p),
            extension=p.suffix.lower(),
            content=content,
            mime_type=mime_type,
            size=len(
                content.encode()
            ),
        )
    @property
    def exists(
        self,
    ) -> bool:

        return Path(
            self.path
        ).exists()

    @property
    def filename(
        self,
    ) -> str:

        return self.name

    @property
    def stem(
        self,
    ) -> str:

        return Path(
            self.name
        ).stem

    @property
    def suffix(
        self,
    ) -> str:

        return self.extension

    def update_content(
        self,
        content: str,
    ) -> None:

        self.content = content

        self.size = len(
            content.encode()
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

    def to_dict(
        self,
    ) -> dict:

        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "content": self.content,
            "mime_type": self.mime_type,
            "extension": self.extension,
            "size": self.size,
            "source": self.source,
            "created_at": (
                self.created_at.isoformat()
            ),
            "metadata": self.metadata,
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