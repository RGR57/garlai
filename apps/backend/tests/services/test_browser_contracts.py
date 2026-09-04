from datetime import datetime, timezone
import json

import pytest

from src.models.browser import BrowserElement, BrowserObservation, BrowserTarget
from src.models.tool_result import ToolInvocationOutcome, ToolResult
from src.tools.base_tool import BaseTool, ToolInvocationContext
from src.tools.tool_manager import ToolManager


class ContextAwareTool(BaseTool):
    @property
    def name(self) -> str:
        return "context_aware"

    @property
    def description(self) -> str:
        return "Records the execution identity supplied by GARL."

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs) -> ToolResult:
        raise AssertionError("ToolManager must use execute_with_context.")

    async def execute_with_context(
        self,
        arguments: dict,
        invocation: ToolInvocationContext,
    ) -> ToolResult:
        return ToolResult(
            success=True,
            tool_name=self.name,
            output={"execution_id": invocation.execution_id},
            invocation_outcome=ToolInvocationOutcome.CONFIRMED,
        )


@pytest.mark.anyio
async def test_tool_manager_routes_executor_owned_context_to_context_aware_tool():
    manager = ToolManager()
    manager.register(ContextAwareTool())

    result = await manager.execute(
        "context_aware",
        {},
        ToolInvocationContext(execution_id="run-42", step_id=7, operation_id="op-9"),
    )

    assert result.output == {"execution_id": "run-42"}
    assert result.invocation_outcome is ToolInvocationOutcome.CONFIRMED


def test_browser_observation_rejects_unbounded_visible_page_content():
    element = BrowserElement(
        element_ref="obs-1:button-1",
        role="button",
        accessible_name="Choose Pro",
        semantic_fingerprint="button|choose pro|pricing",
    )

    with pytest.raises(ValueError, match="visible_text"):
        BrowserObservation(
            observation_id="obs-1",
            browser_session_id="browser-run-42",
            url="https://market.example/pricing",
            title="Pricing",
            visible_text="x" * 12_001,
            elements=(element,),
            observed_at=datetime.now(timezone.utc),
            navigation_sequence=1,
            page_fingerprint="pricing-v1",
        )


def test_browser_target_requires_semantic_identity_not_only_a_local_reference():
    with pytest.raises(ValueError, match="semantic_fingerprint"):
        BrowserTarget(
            browser_session_id="browser-run-42",
            observation_id="obs-1",
            element_ref="obs-1:button-1",
            observed_url="https://market.example/pricing",
            role="button",
            accessible_name="Choose Pro",
            label=None,
            form_name=None,
            text_context="",
            semantic_fingerprint="",
        )


def test_browser_observation_serializes_as_bounded_json_facts():
    observation = BrowserObservation(
        observation_id="obs-1",
        browser_session_id="browser-run-42",
        url="https://market.example/pricing",
        title="Pricing",
        visible_text="Pro supports SSO.",
        elements=(
            BrowserElement(
                element_ref="obs-1:button-1",
                role="button",
                accessible_name="Choose Pro",
                semantic_fingerprint="button|choose pro|pricing",
            ),
        ),
        observed_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
        navigation_sequence=1,
        page_fingerprint="pricing-v1",
    )

    payload = observation.to_payload()

    assert json.loads(json.dumps(payload)) == {
        "observation_id": "obs-1",
        "browser_session_id": "browser-run-42",
        "url": "https://market.example/pricing",
        "title": "Pricing",
        "visible_text": "Pro supports SSO.",
        "elements": [
            {
                "element_ref": "obs-1:button-1",
                "role": "button",
                "accessible_name": "Choose Pro",
                "semantic_fingerprint": "button|choose pro|pricing",
                "label": None,
                "form_name": None,
                "text_context": "",
                "is_sensitive": False,
            }
        ],
        "observed_at": "2026-09-04T00:00:00+00:00",
        "navigation_sequence": 1,
        "page_fingerprint": "pricing-v1",
    }
