from __future__ import annotations

from typing import Protocol

from src.models.browser import BrowserObservation, BrowserTarget


class NavigationPolicy(Protocol):
    """Decides whether a document URL is safe before provider navigation."""

    def validate(self, url: str) -> str:
        """Return the normalized allowed URL or raise ValueError."""


class BrowserProvider(Protocol):
    """Technology boundary; handles are opaque to GARL services and tools."""

    async def create_session(self, browser_session_id: str) -> object:
        """Create one ephemeral provider session."""

    async def close_session(self, session: object) -> None:
        """Release an ephemeral provider session."""

    async def navigate(
        self,
        session: object,
        url: str,
        navigation_policy: NavigationPolicy,
    ) -> str:
        """Navigate after provider-level policy enforcement and return final URL."""

    async def observe(self, session: object) -> BrowserObservation:
        """Return bounded, structured page facts."""

    async def select(self, session: object, target: BrowserTarget) -> None:
        """Perform a semantic preparatory selection."""

    async def fill(self, session: object, target: BrowserTarget, value: str) -> None:
        """Fill one non-sensitive semantic field."""

    async def submit(self, session: object, target: BrowserTarget) -> None:
        """Perform one semantic final commitment dispatch."""
