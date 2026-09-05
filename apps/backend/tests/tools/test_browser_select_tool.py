import pytest

from src.models.tool_result import ToolInvocationOutcome
from src.tools.base_tool import ToolInvocationContext
from src.tools.browser.browser_select_tool import BrowserSelectTool


def target_payload() -> dict[str, object]:
    return {
        "browser_session_id": "browser-run-42",
        "observation_id": "obs-1",
        "element_ref": "obs-1:pro",
        "observed_url": "https://market.example/pricing",
        "role": "button",
        "accessible_name": "Choose Pro",
        "label": None,
        "form_name": None,
        "text_context": "Supports SSO.",
        "semantic_fingerprint": "button|choose pro|pricing",
        "is_sensitive": False,
    }


class RecordingBrowserSessionService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, str]] = []

    async def select(self, execution_id: str, target, operation_id: str) -> dict[str, object]:
        self.calls.append((execution_id, target, operation_id))
        return {"action": "select", "target": target.to_payload()}


@pytest.mark.anyio
async def test_select_requires_a_complete_target_and_records_a_confirmed_receipt():
    service = RecordingBrowserSessionService()
    tool = BrowserSelectTool(service)

    result = await tool.execute_with_context(
        {"target": target_payload()},
        ToolInvocationContext(execution_id="run-42", step_id=3, operation_id="op-select"),
    )

    assert len(service.calls) == 1
    assert service.calls[0][0] == "run-42"
    assert service.calls[0][1].element_ref == "obs-1:pro"
    assert service.calls[0][2] == "op-select"
    assert result.output["receipt"]["action"] == "select"
    assert result.invocation_outcome is ToolInvocationOutcome.CONFIRMED
