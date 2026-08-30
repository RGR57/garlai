from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class MemoryType(str, Enum):

    FACT = "fact"
    PREFERENCE = "preference"
    DECISION = "decision"
    CONTEXT = "context"
    RESULT = "result"


@dataclass
class Memory:

    id: str

    content: str

    created_at: datetime

    memory_type: MemoryType = MemoryType.CONTEXT

    importance: float = 0.5

    access_count: int = 0

    last_accessed_at: datetime | None = None

    def touch(self) -> None:

        self.access_count += 1

        self.last_accessed_at = (
            datetime.now(timezone.utc)
        )