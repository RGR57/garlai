from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from src.models.browser import BrowserObservation, BrowserTarget
from src.services.browser_provider import NavigationPolicy


@dataclass
class _FakeBrowserSession:
    browser_session_id: str
    current_url: str | None = None
    closed: bool = False


class FakeBrowserProvider:
    """Deterministic provider with frozen observations and no network behavior."""

    def __init__(self, pages: Mapping[str, BrowserObservation]) -> None:
        self._pages = dict(pages)
        self.actions: list[tuple[str, BrowserTarget]] = []

    async def create_session(self, browser_session_id: str) -> object:
        return _FakeBrowserSession(browser_session_id=browser_session_id)

    async def close_session(self, session: object) -> None:
        fake_session = self._session(session)
        fake_session.closed = True

    async def navigate(
        self,
        session: object,
        url: str,
        navigation_policy: NavigationPolicy,
    ) -> str:
        fake_session = self._session(session)
        normalized = navigation_policy.validate(url)
        fake_session.current_url = normalized
        return normalized

    async def observe(self, session: object) -> BrowserObservation:
        fake_session = self._session(session)
        if fake_session.current_url is None:
            raise ValueError("Browser session has no current page.")
        observation = self._pages.get(fake_session.current_url)
        if observation is None:
            raise ValueError("Browser session current page has no fixture observation.")
        return replace(observation, browser_session_id=fake_session.browser_session_id)

    async def select(self, session: object, target: BrowserTarget) -> None:
        self._assert_open(session)
        self.actions.append(("select", target))

    async def fill(self, session: object, target: BrowserTarget, value: str) -> None:
        self._assert_open(session)
        self.actions.append(("fill", target))

    async def submit(self, session: object, target: BrowserTarget) -> None:
        self._assert_open(session)
        self.actions.append(("submit", target))

    @staticmethod
    def _session(session: object) -> _FakeBrowserSession:
        if not isinstance(session, _FakeBrowserSession):
            raise ValueError("Fake browser provider received an invalid session.")
        if session.closed:
            raise ValueError("Browser session is closed.")
        return session

    def _assert_open(self, session: object) -> None:
        self._session(session)
