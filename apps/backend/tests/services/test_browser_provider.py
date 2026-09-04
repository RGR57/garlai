from datetime import datetime, timezone

import pytest

from src.models.browser import BrowserElement, BrowserObservation, BrowserTarget
from src.services.fake_browser_provider import FakeBrowserProvider
from src.services.navigation_policy import LocalFixtureNavigationPolicy
from src.services.playwright_browser_provider import (
    PlaywrightBrowserProvider,
    _PlaywrightBrowserSession,
    _to_browser_element,
)


@pytest.mark.anyio
async def test_fake_provider_observes_a_frozen_accessibility_fixture_after_navigation():
    url = "http://127.0.0.1:8123/pricing"
    provider = FakeBrowserProvider(
        pages={
            url: BrowserObservation(
                observation_id="fixture-pricing",
                browser_session_id="fixture-session",
                url=url,
                title="Pricing",
                visible_text="Pro supports SSO and 20 users.",
                elements=(
                    BrowserElement(
                        element_ref="fixture-pricing:pro",
                        role="button",
                        accessible_name="Choose Pro",
                        semantic_fingerprint="button|choose pro|pricing",
                    ),
                ),
                observed_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
                navigation_sequence=1,
                page_fingerprint="fixture-pricing-v1",
            )
        }
    )
    session = await provider.create_session("run-42")

    await provider.navigate(session, url, LocalFixtureNavigationPolicy("http://127.0.0.1:8123"))
    observation = await provider.observe(session)

    assert observation.browser_session_id == "run-42"
    assert observation.elements[0].accessible_name == "Choose Pro"


@pytest.mark.anyio
async def test_fake_provider_does_not_change_page_when_navigation_policy_rejects_url():
    provider = FakeBrowserProvider(pages={})
    session = await provider.create_session("run-42")

    with pytest.raises(ValueError):
        await provider.navigate(
            session,
            "http://127.0.0.1:8124/pricing",
            LocalFixtureNavigationPolicy("http://127.0.0.1:8123"),
        )

    with pytest.raises(ValueError, match="no current page"):
        await provider.observe(session)


class _RecordingLocator:
    def __init__(self) -> None:
        self.click_count = 0
        self.select_option_count = 0

    async def count(self) -> int:
        return 1

    async def click(self) -> None:
        self.click_count += 1

    async def select_option(self, **kwargs) -> None:
        self.select_option_count += 1


class _RecordingPage:
    def __init__(self, locator: _RecordingLocator) -> None:
        self.locator = locator

    def get_by_role(self, role: str, *, name: str, exact: bool):
        assert (role, name, exact) == ("button", "Choose Pro", True)
        return self.locator


@pytest.mark.anyio
async def test_playwright_provider_select_activates_the_semantic_plan_choice():
    locator = _RecordingLocator()
    session = _PlaywrightBrowserSession(
        runtime=None,
        browser=None,
        context=None,
        page=_RecordingPage(locator),
        browser_session_id="run-42",
    )

    await PlaywrightBrowserProvider().select(
        session,
        BrowserTarget(
            browser_session_id="run-42",
            observation_id="obs-1",
            element_ref="obs-1:pro",
            observed_url="https://market.example/pricing",
            role="button",
            accessible_name="Choose Pro",
            label=None,
            form_name=None,
            text_context="Pro supports SSO.",
            semantic_fingerprint="button|choose pro|pricing",
        ),
    )

    assert locator.click_count == 1
    assert locator.select_option_count == 0


def test_playwright_observation_never_uses_a_password_value_as_an_element_name():
    element = _to_browser_element(
        "obs-1",
        {
            "index": 0,
            "tag_name": "INPUT",
            "role": "textbox",
            "aria_label": None,
            "label": "Password",
            "text": "",
            "name": "password",
            "placeholder": "",
            "input_type": "password",
            "button_value": None,
            "text_context": "Sign in",
        },
    )

    assert element.accessible_name == "Password"
    assert "secret" not in element.accessible_name.lower()
    assert element.is_sensitive is True
