from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ConversationMessage:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)