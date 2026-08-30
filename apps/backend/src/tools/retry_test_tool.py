from src.models.tool_result import ToolResult
from src.tools.base_tool import BaseTool


class RetryTestTool(BaseTool):
    """
    Development tool used to verify GARL's RETRY behavior.

    First execution:
        fails with a transient error.

    Second execution:
        succeeds.

    This allows us to verify that RETRY re-executes
    the existing plan instead of invoking the planner again.
    """

    def __init__(self):
        self._attempts = 0

    @property
    def name(self) -> str:
        return "retry_test"

    @property
    def description(self) -> str:
        return (
            "Development test tool that temporarily fails "
            "once and succeeds on the next execution."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Value used for the retry test.",
                }
            },
            "required": ["query"],
        }

    async def execute(
        self,
        **kwargs,
    ) -> ToolResult:

        self._attempts += 1

        query = kwargs.get("query", "")

        if self._attempts == 1:

            return ToolResult(
                success=False,
                tool_name=self.name,
                output=None,
                metadata={
                    "error": (
                        "Temporarily unavailable. "
                        "Retry test failure."
                    ),
                    "attempt": self._attempts,
                    "query": query,
                },
            )

        return ToolResult(
            success=True,
            tool_name=self.name,
            output=(
                "Retry test succeeded on "
                f"attempt {self._attempts}."
            ),
            metadata={
                "attempt": self._attempts,
                "query": query,
            },
        )