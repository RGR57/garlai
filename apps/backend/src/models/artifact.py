from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ArtifactType(str, Enum):

    PYTHON = "python"

    TEXT = "text"

    JSON = "json"

    CSV = "csv"

    MARKDOWN = "markdown"

    IMAGE = "image"

    PDF = "pdf"

    DIRECTORY = "directory"

    UNKNOWN = "unknown"


@dataclass
class Artifact:

    id: str

    name: str

    artifact_type: ArtifactType

    path: str

    created_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    preview: str = ""

    metadata: dict[str, Any] = field(
        default_factory=dict
    )
