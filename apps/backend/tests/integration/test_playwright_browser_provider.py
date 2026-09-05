import pytest

from src.models.browser import BrowserTarget
from src.services.navigation_policy import LocalFixtureNavigationPolicy
from src.services.playwright_browser_provider import PlaywrightBrowserProvider


def _target(observation, accessible_name: str) -> BrowserTarget:
    element = next(
        item for item in observation.elements if item.accessible_name == accessible_name
    )
    return BrowserTarget(
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


@pytest.mark.anyio
async def test_playwright_provider_observes_semantic_plan_cards(local_marketplace):
    provider = PlaywrightBrowserProvider()
    session = await provider.create_session("browser-local-marketplace")
    try:
        await provider.navigate(
            session,
            local_marketplace.url("/"),
            LocalFixtureNavigationPolicy(local_marketplace.origin),
        )

        observation = await provider.observe(session)

        assert {element.accessible_name for element in observation.elements} >= {
            "Choose Starter",
            "Choose Pro",
            "Choose Business",
        }
        assert "Business" in observation.visible_text
    finally:
        await provider.close_session(session)


@pytest.mark.anyio
async def test_fixture_records_commit_only_after_final_submit(local_marketplace):
    provider = PlaywrightBrowserProvider()
    session = await provider.create_session("browser-local-marketplace")
    try:
        policy = LocalFixtureNavigationPolicy(local_marketplace.origin)
        await provider.navigate(session, local_marketplace.url("/"), policy)
        pricing = await provider.observe(session)
        await provider.select(session, _target(pricing, "Choose Business"))

        review = await provider.observe(session)
        await provider.fill(session, _target(review, "Name"), "GARL Test")
        assert await local_marketplace.commit_count() == 0
        await provider.submit(session, _target(review, "Confirm Business signup"))

        confirmation = await provider.observe(session)
        assert "Signup complete" in confirmation.visible_text
        assert await local_marketplace.commit_count() == 1
    finally:
        await provider.close_session(session)
