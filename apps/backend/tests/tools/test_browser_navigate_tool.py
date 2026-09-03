import pytest

from src.models.tool_result import ToolInvocationOutcome
from src.tools.base_tool import ToolInvocationContext
from src.tools.browser.browser_navigate_tool import BrowserNavigateTool


class RecordingBrowserSessionService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def navigate(self, execution_id: str, url: str) -> str:
        self.calls.append((execution_id, url))
        return "https://market.example/pricing"


@pytest.mark.anyio
async def test_navigate_uses_executor_owned_identity_and_returns_verified_url():
    service = RecordingBrowserSessionService()
    tool = BrowserNavigateTool(service)

    result = await tool.execute_with_context(
        {"url": "https://market.example/pricing"},
        ToolInvocationContext(execution_id="run-42", step_id=1, operation_id="op-1"),
    )

    assert service.calls == [("run-42", "https://market.example/pricing")]
    assert result.output == {
        "browser_session_execution_id": "run-42",
        "url": "https://market.example/pricing",
    }
    assert result.invocation_outcome is ToolInvocationOutcome.CONFIRMED
