from dataclasses import dataclass
from enum import Enum
from typing import Any


class ToolInvocationOutcome(str, Enum):
    """What a tool can prove about an attempted external dispatch."""

    NOT_INVOKED = "not_invoked"
    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"


@dataclass
class ToolResult:
    success: bool
    tool_name: str
    output: Any
    metadata: dict | None = None
    invocation_outcome: ToolInvocationOutcome | None = None
