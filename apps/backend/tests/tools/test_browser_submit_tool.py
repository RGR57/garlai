import pytest

from src.models.tool_result import ToolInvocationOutcome, ToolResult
from src.tools.base_tool import ToolInvocationContext
from src.tools.browser.browser_submit_tool import BrowserSubmitTool
from src.tools.tool_manager import ToolManager


def target_payload() -> dict[str, object]:
    return {
        "browser_session_id": "browser-run-42", "observation_id": "obs-1",
        "element_ref": "obs-1:confirm", "observed_url": "https://market.example/signup",
        "role": "button", "accessible_name": "Confirm signup", "label": None,
        "form_name": "Signup", "text_context": "Confirm Pro at $30/month.",
        "semantic_fingerprint": "button|confirm signup|pro", "is_sensitive": False,
    }


class RecordingBrowserSessionService:
    def __init__(self, ready: bool) -> None:
        self.ready = ready
        self.preflight_calls = []
        self.submit_calls = []

    async def preflight_submit(self, execution_id, target, operation_id):
        self.preflight_calls.append((execution_id, target, operation_id))
        return self.ready, "target changed" if not self.ready else None

    async def submit(self, execution_id, target, operation_id):
        self.submit_calls.append((execution_id, target, operation_id))
        return {"action": "submit", "target": target.to_payload()}


@pytest.mark.anyio
async def test_submit_preflight_blocks_stale_target_before_provider_dispatch():
    service = RecordingBrowserSessionService(ready=False)
    tool = BrowserSubmitTool(service)
    context = ToolInvocationContext("run-42", 5, "op-submit", "approved-hash")

    preflight = await tool.preflight({"target": target_payload()}, context)

    assert preflight.ready is False
    assert preflight.reason == "target changed"
    assert service.submit_calls == []


@pytest.mark.anyio
async def test_submit_executes_only_with_approved_context_after_ready_preflight():
    service = RecordingBrowserSessionService(ready=True)
    tool = BrowserSubmitTool(service)
    context = ToolInvocationContext("run-42", 5, "op-submit", "approved-hash")

    result = await tool.execute_with_context({"target": target_payload()}, context)

    assert len(service.submit_calls) == 1
    assert result.invocation_outcome is ToolInvocationOutcome.CONFIRMED


def test_submit_schema_freezes_a_non_sensitive_visible_success_proof():
    manager = ToolManager()
    manager.register(BrowserSubmitTool(RecordingBrowserSessionService(ready=True)))

    valid, error = manager.validate_arguments(
        "browser_submit",
        {"target": target_payload(), "expected_success_text": "Signup complete"},
    )

    assert valid is True
    assert error is None
