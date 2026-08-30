from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Event:

    name: str

    payload: Any

    timestamp: datetime