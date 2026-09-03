from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.models.browser import BrowserObservation
from src.repositories.durable_execution_repository import DurableExecutionRepository
from src.services.browser_provider import BrowserProvider, NavigationPolicy


@dataclass
class BrowserSession:
    """Ephemeral provider state owned by exactly one durable execution."""

    execution_id: str
    browser_session_id: str
    provider_session: object


class BrowserSessionService:
    """Own browser mechanics without choosing or executing GARL plans."""

    def __init__(
        self,
        repository: DurableExecutionRepository,
        provider: BrowserProvider,
        navigation_policy: NavigationPolicy,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.navigation_policy = navigation_policy
        self._sessions: dict[str, BrowserSession] = {}

    async def get_or_create(self, execution_id: str) -> BrowserSession:
        existing = self._sessions.get(execution_id)
        if existing is not None:
            return existing

        run = await self.repository.load(execution_id)
        browser_facts = run.execution_context.get("browser")
        browser_session_id = (
            browser_facts.get("session_id")
            if isinstance(browser_facts, dict)
            else None
        )
        if not isinstance(browser_session_id, str) or not browser_session_id:
            browser_session_id = f"browser-{execution_id}"
            await self.repository.patch_execution_context(
                execution_id,
                {"browser": {"session_id": browser_session_id}},
            )

        session = BrowserSession(
            execution_id=execution_id,
            browser_session_id=browser_session_id,
            provider_session=await self.provider.create_session(browser_session_id),
        )
        self._sessions[execution_id] = session
        return session

    async def navigate(self, execution_id: str, url: str) -> str:
        session = await self.get_or_create(execution_id)
        final_url = await self.provider.navigate(
            session.provider_session,
            url,
            self.navigation_policy,
        )
        await self.repository.patch_execution_context(
            execution_id,
            {
                "browser": {
                    "session_id": session.browser_session_id,
                    "last_verified_url": final_url,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        return final_url

    async def observe(self, execution_id: str) -> BrowserObservation:
        session = await self.get_or_create(execution_id)
        observation = await self.provider.observe(session.provider_session)
        if observation.browser_session_id != session.browser_session_id:
            raise ValueError("Browser provider observation does not belong to the execution session.")
        await self.repository.patch_execution_context(
            execution_id,
            {
                "browser": {
                    "session_id": session.browser_session_id,
                    "last_verified_url": observation.url,
                    "latest_observation": observation.to_payload(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        return observation

    async def close_execution(self, execution_id: str) -> None:
        session = self._sessions.pop(execution_id, None)
        if session is not None:
            await self.provider.close_session(session.provider_session)
