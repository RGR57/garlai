from dataclasses import dataclass, field

from src.models.artifact import Artifact


@dataclass
class ChatResponse:

    response: str

    artifacts: list[Artifact] = field(
        default_factory=list
    )