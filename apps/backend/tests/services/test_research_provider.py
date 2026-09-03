import asyncio

import pytest

from src.services.brave_research_provider import BraveResearchProvider
from src.services.research_provider import FakeResearchProvider, ResearchProviderError


def test_fake_research_provider_returns_deterministic_evidence():
    result = asyncio.run(FakeResearchProvider().search("GARL market"))

    assert result.query == "GARL market"
    assert result.evidence[0].url == "https://example.test/garl-market"
    assert result.evidence[0].title == "Deterministic GARL market evidence"


def test_fake_research_provider_rejects_empty_query():
    with pytest.raises(ResearchProviderError, match="query must not be empty"):
        asyncio.run(FakeResearchProvider().search("  "))


def test_brave_provider_normalizes_vendor_response_without_network_access():
    async def transport(url: str, headers: dict[str, str]) -> dict:
        assert url.startswith("https://api.search.brave.com/res/v1/web/search?")
        assert headers["X-Subscription-Token"] == "test-key"
        return {
            "web": {
                "results": [
                    {
                        "title": "Primary source",
                        "url": "https://example.test/source",
                        "description": "Observed market fact.",
                    }
                ]
            }
        }

    result = asyncio.run(
        BraveResearchProvider(api_key="test-key", transport=transport).search(
            "market evidence", count=1
        )
    )

    assert result.evidence[0].source == "brave"
    assert result.evidence[0].url == "https://example.test/source"
