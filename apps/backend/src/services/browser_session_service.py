from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

from src.models.browser import BrowserObservation, BrowserTarget
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

    async def select(
        self,
        execution_id: str,
        target: BrowserTarget,
        operation_id: str,
    ) -> dict[str, object]:
        session, observation = await self._resolve_target(execution_id, target, operation_id)
        await self.provider.select(session.provider_session, target)
        receipt = self._receipt("select", target, observation)
        await self._record_action(execution_id, operation_id, receipt)
        return receipt

    async def fill(
        self,
        execution_id: str,
        target: BrowserTarget,
        value: str,
        operation_id: str,
    ) -> dict[str, object]:
        if target.is_sensitive:
            raise ValueError("Browser fill refuses a sensitive field.")
        if not isinstance(value, str) or not value:
            raise ValueError("Browser fill value must be a non-empty string.")
        session, observation = await self._resolve_target(execution_id, target, operation_id)
        await self.provider.fill(session.provider_session, target, value)
        receipt = self._receipt(
            "fill",
            target,
            observation,
            value_hash=hashlib.sha256(value.encode("utf-8")).hexdigest(),
        )
        await self._record_action(execution_id, operation_id, receipt)
        return receipt

    async def preflight_submit(
        self,
        execution_id: str,
        target: BrowserTarget,
        operation_id: str,
    ) -> tuple[bool, str | None]:
        try:
            await self._resolve_target(execution_id, target, operation_id)
        except ValueError as exc:
            return False, str(exc)
        return True, None

    async def submit(
        self,
        execution_id: str,
        target: BrowserTarget,
        operation_id: str,
    ) -> dict[str, object]:
        session = await self.get_or_create(execution_id)
        if target.browser_session_id != session.browser_session_id:
            raise ValueError("Browser target belongs to a different execution session.")
        await self.provider.submit(session.provider_session, target)
        observation = await self.provider.observe(session.provider_session)
        receipt = self._receipt("submit", target, observation)
        await self._record_action(execution_id, operation_id, receipt)
        return receipt

    async def _resolve_target(
        self,
        execution_id: str,
        target: BrowserTarget,
        operation_id: str,
    ) -> tuple[BrowserSession, BrowserObservation]:
        if not operation_id:
            raise ValueError("Browser preparation requires a durable operation identity.")
        session = await self.get_or_create(execution_id)
        if target.browser_session_id != session.browser_session_id:
            raise ValueError("Browser target belongs to a different execution session.")
        observation = await self.provider.observe(session.provider_session)
        matches = [
            element
            for element in observation.elements
            if element.role == target.role
            and element.accessible_name == target.accessible_name
            and element.label == target.label
            and element.form_name == target.form_name
            and element.text_context == target.text_context
            and element.semantic_fingerprint == target.semantic_fingerprint
            and element.is_sensitive == target.is_sensitive
        ]
        if len(matches) != 1 or observation.url != target.observed_url:
            raise ValueError("Browser target is missing, changed, or ambiguous on the current page.")
        return session, observation

    @staticmethod
    def _receipt(
        action: str,
        target: BrowserTarget,
        observation: BrowserObservation,
        *,
        value_hash: str | None = None,
    ) -> dict[str, object]:
        receipt: dict[str, object] = {
            "action": action,
            "target": target.to_payload(),
            "observed_url": observation.url,
            "observation_id": observation.observation_id,
            "observed_at": observation.observed_at.isoformat(),
        }
        if value_hash is not None:
            receipt["value_hash"] = value_hash
        return receipt

    async def _record_action(
        self,
        execution_id: str,
        operation_id: str,
        receipt: dict[str, object],
    ) -> None:
        await self.repository.patch_execution_context(
            execution_id,
            {
                "browser": {
                    "actions": {operation_id: receipt},
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

    async def close_execution(self, execution_id: str) -> None:
        session = self._sessions.pop(execution_id, None)
        if session is not None:
            await self.provider.close_session(session.provider_session)
