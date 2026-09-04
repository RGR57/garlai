import pytest

from src.models.tool_result import ToolInvocationOutcome
from src.tools.base_tool import ToolInvocationContext
from src.tools.browser.browser_fill_tool import BrowserFillTool


def target_payload(*, is_sensitive: bool = False) -> dict[str, object]:
    return {
        "browser_session_id": "browser-run-42",
        "observation_id": "obs-1",
        "element_ref": "obs-1:name",
        "observed_url": "https://market.example/signup",
        "role": "textbox",
        "accessible_name": "Full name" if not is_sensitive else "Password",
        "label": "Full name" if not is_sensitive else "Password",
        "form_name": "Signup",
        "text_context": "Test details",
        "semantic_fingerprint": "textbox|name|signup",
        "is_sensitive": is_sensitive,
    }


class RecordingBrowserSessionService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, str, str]] = []

    async def fill(self, execution_id: str, target, value: str, operation_id: str) -> dict[str, object]:
        self.calls.append((execution_id, target, value, operation_id))
        return {
            "action": "fill",
            "field": target.element_ref,
            "value_hash": "sha256:test",
        }


@pytest.mark.anyio
async def test_fill_records_a_receipt_without_the_literal_value():
    service = RecordingBrowserSessionService()
    tool = BrowserFillTool(service)

    result = await tool.execute_with_context(
        {"target": target_payload(), "value": "Ada Test"},
        ToolInvocationContext(execution_id="run-42", step_id=4, operation_id="op-fill"),
    )

    assert service.calls[0][2] == "Ada Test"
    assert result.output["receipt"] == {
        "action": "fill",
        "field": "obs-1:name",
        "value_hash": "sha256:test",
    }
    assert "Ada Test" not in str(result.output)
    assert result.invocation_outcome is ToolInvocationOutcome.CONFIRMED


@pytest.mark.anyio
async def test_fill_rejects_password_like_field_without_provider_dispatch():
    service = RecordingBrowserSessionService()
    tool = BrowserFillTool(service)

    with pytest.raises(ValueError, match="sensitive"):
        await tool.execute_with_context(
            {"target": target_payload(is_sensitive=True), "value": "not-a-real-secret"},
            ToolInvocationContext(execution_id="run-42", step_id=4, operation_id="op-fill"),
        )

    assert service.calls == []
