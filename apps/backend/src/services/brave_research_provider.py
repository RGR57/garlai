from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.services.research_provider import (
    ResearchEvidence,
    ResearchProviderError,
    ResearchResult,
)


Transport = Callable[[str, dict[str, str]], Awaitable[dict[str, Any]]]


class BraveResearchProvider:
    BASE_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 10.0,
        transport: Transport | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self.transport = transport or self._request

    async def search(self, query: str, *, count: int = 5) -> ResearchResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise ResearchProviderError("Research query must not be empty.")
        if not self.api_key:
            raise ResearchProviderError("Brave Search API key is not configured.")
        if count <= 0:
            raise ResearchProviderError("Research result count must be positive.")
        url = f"{self.BASE_URL}?{urlencode({'q': normalized_query, 'count': count})}"
        try:
            payload = await self.transport(
                url,
                {"Accept": "application/json", "X-Subscription-Token": self.api_key},
            )
        except ResearchProviderError:
            raise
        except Exception as exc:
            raise ResearchProviderError("Brave research request failed.") from exc
        results = payload.get("web", {}).get("results", [])
        if not isinstance(results, list):
            raise ResearchProviderError("Brave research response was malformed.")
        evidence = tuple(
            ResearchEvidence(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                snippet=str(item.get("description", "")),
                source="brave",
            )
            for item in results[:count]
            if isinstance(item, dict) and item.get("url")
        )
        return ResearchResult(query=normalized_query, evidence=evidence)

    async def _request(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        def request() -> dict[str, Any]:
            with urlopen(Request(url, headers=headers), timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))

        return await asyncio.to_thread(request)
