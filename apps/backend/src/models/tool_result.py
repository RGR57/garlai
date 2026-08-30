from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    success: bool
    tool_name: str
    output: Any
    metadata: dict | None = None