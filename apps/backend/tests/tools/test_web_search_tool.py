import asyncio

from src.models.tool_risk import PermissionDecision
from src.services.execution_policy import ExecutionClassification
from src.services.permission_service import PermissionService
from src.services.research_provider import FakeResearchProvider
from src.tools.web_search_tool import WebSearchTool


def test_web_search_returns_source_backed_evidence_and_is_read_only():
    result = asyncio.run(WebSearchTool(FakeResearchProvider()).execute("GARL market"))
    permission = PermissionService().evaluate("web_search", {"query": "GARL market"})

    assert result.success is True
    assert result.output["evidence"][0]["url"] == "https://example.test/garl-market"
    assert permission.decision is PermissionDecision.ALLOW
    assert permission.execution_policy.classification is ExecutionClassification.READ_ONLY
