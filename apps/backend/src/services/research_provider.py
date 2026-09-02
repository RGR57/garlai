from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ResearchProviderError(ValueError):
    pass


@dataclass(frozen=True)
class ResearchEvidence:
    title: str
    url: str
    snippet: str
    source: str


@dataclass(frozen=True)
class ResearchResult:
    query: str
    evidence: tuple[ResearchEvidence, ...]


class ResearchProvider(Protocol):
    async def search(self, query: str, *, count: int = 5) -> ResearchResult:
        ...


class FakeResearchProvider:
    async def search(self, query: str, *, count: int = 5) -> ResearchResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise ResearchProviderError("Research query must not be empty.")
        if count <= 0:
            raise ResearchProviderError("Research result count must be positive.")
        return ResearchResult(
            query=normalized_query,
            evidence=(
                ResearchEvidence(
                    title="Deterministic GARL market evidence",
                    url="https://example.test/garl-market",
                    snippet="Deterministic evidence for offline GARL tests.",
                    source="fake",
                ),
            )[:count],
        )
