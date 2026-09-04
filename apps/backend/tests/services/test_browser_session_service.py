from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from src.models.browser import BrowserElement, BrowserObservation, BrowserTarget
from src.models.durable_execution import ExecutionRun
from src.repositories.sqlite_durable_execution_repository import (
    SQLiteDurableExecutionRepository,
)
from src.services.browser_session_service import BrowserSessionService
from src.services.fake_browser_provider import FakeBrowserProvider
from src.services.navigation_policy import LocalFixtureNavigationPolicy


class BrowserSessionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.repository = SQLiteDurableExecutionRepository(
            Path(self._directory.name) / "browser.sqlite3"
        )
        await self.repository.initialize()
        for execution_id in ("run-a", "run-b"):
            await self.repository.create_planning_run(
                ExecutionRun(
                    execution_id=execution_id,
                    objective="Inspect a local marketplace.",
                    execution_context={"source": "test"},
                )
            )
        self.url = "http://127.0.0.1:8123/pricing"
        self.provider = FakeBrowserProvider(
            {
                self.url: BrowserObservation(
                    observation_id="pricing-observation",
                    browser_session_id="fixture-session",
                    url=self.url,
                    title="Pricing",
                    visible_text="Pro supports SSO.",
                    elements=(
                        BrowserElement(
                            element_ref="pricing-observation:pro",
                            role="button",
                            accessible_name="Choose Pro",
                            semantic_fingerprint="button|choose pro|pricing",
                        ),
                    ),
                    observed_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
                    navigation_sequence=1,
                    page_fingerprint="pricing-v1",
                )
            }
        )
        self.policy = LocalFixtureNavigationPolicy("http://127.0.0.1:8123")

    async def test_browser_sessions_are_isolated_by_execution_id_not_conversation(self):
        service = BrowserSessionService(self.repository, self.provider, self.policy)

        first = await service.get_or_create("run-a")
        second = await service.get_or_create("run-b")

        self.assertNotEqual(first.browser_session_id, second.browser_session_id)
        self.assertNotEqual(first.provider_session, second.provider_session)
        self.assertEqual(
            (await self.repository.load("run-a")).execution_context["browser"]["session_id"],
            first.browser_session_id,
        )

    async def test_fresh_service_reuses_durable_session_identity_and_browser_facts(self):
        first = BrowserSessionService(self.repository, self.provider, self.policy)
        first_session = await first.get_or_create("run-a")
        await first.navigate("run-a", self.url)
        observation = await first.observe("run-a")

        fresh = BrowserSessionService(self.repository, self.provider, self.policy)
        recovered_session = await fresh.get_or_create("run-a")
        loaded = await self.repository.load("run-a")

        self.assertEqual(recovered_session.browser_session_id, first_session.browser_session_id)
        self.assertEqual(loaded.execution_context["browser"]["last_verified_url"], self.url)
        self.assertEqual(
            loaded.execution_context["browser"]["latest_observation"],
            observation.to_payload(),
        )

    async def test_fill_persists_a_value_hash_but_never_the_literal_value(self):
        service = BrowserSessionService(self.repository, self.provider, self.policy)
        await service.navigate("run-a", self.url)
        observation = await service.observe("run-a")
        element = observation.elements[0]
        target = BrowserTarget(
            browser_session_id=observation.browser_session_id,
            observation_id=observation.observation_id,
            element_ref=element.element_ref,
            observed_url=observation.url,
            role=element.role,
            accessible_name=element.accessible_name,
            label=element.label,
            form_name=element.form_name,
            text_context=element.text_context,
            semantic_fingerprint=element.semantic_fingerprint,
            is_sensitive=element.is_sensitive,
        )

        receipt = await service.fill("run-a", target, "Ada Test", "op-fill")
        loaded = await self.repository.load("run-a")

        self.assertEqual(receipt["action"], "fill")
        self.assertIn("value_hash", receipt)
        self.assertNotIn("Ada Test", str(loaded.execution_context))
        self.assertEqual(self.provider.actions, [("fill", target)])
