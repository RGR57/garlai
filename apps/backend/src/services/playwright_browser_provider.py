from __future__ import annotations

import asyncio
import hashlib
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

from src.models.browser import BrowserElement, BrowserObservation, BrowserTarget
from src.services.browser_provider import NavigationPolicy


def _fingerprint(*parts: str) -> str:
    payload = "\x1f".join(part.strip() for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _to_browser_element(observation_id: str, item: dict) -> BrowserElement:
    """Normalize provider facts without accepting input values as page semantics."""
    def text(name: str) -> str:
        value = item.get(name)
        return value.strip() if isinstance(value, str) else ""

    tag_name = text("tag_name") or "ELEMENT"
    role = text("role") or "generic"
    accessible_name = (
        text("aria_label")
        or text("label")
        or text("text")
        or text("name")
        or text("placeholder")
        or text("button_value")
        or tag_name
    )
    text_context = text("text_context")[:500]
    return BrowserElement(
        element_ref=f"{observation_id}:element-{item['index']}",
        role=role,
        accessible_name=accessible_name,
        label=text("label") or None,
        form_name=text("form_name") or None,
        text_context=text_context,
        semantic_fingerprint=_fingerprint(role, accessible_name, text_context),
    )


@dataclass
class _PlaywrightBrowserSession:
    runtime: object
    browser: object
    context: object
    page: object
    browser_session_id: str
    navigation_sequence: int = 0


class PlaywrightBrowserProvider:
    """Playwright adapter that keeps every Playwright object outside GARL state."""

    def __init__(self, *, headless: bool = True) -> None:
        self.headless = headless

    async def create_session(self, browser_session_id: str) -> object:
        try:
            from playwright.async_api import async_playwright
        except ModuleNotFoundError as exc:
            raise RuntimeError("Playwright is not installed for the configured browser provider.") from exc
        runtime = await async_playwright().start()
        browser = await runtime.chromium.launch(headless=self.headless)
        context = await browser.new_context()
        page = await context.new_page()
        return _PlaywrightBrowserSession(
            runtime=runtime,
            browser=browser,
            context=context,
            page=page,
            browser_session_id=browser_session_id,
        )

    async def close_session(self, session: object) -> None:
        browser_session = self._session(session)
        await browser_session.context.close()
        await browser_session.browser.close()
        await browser_session.runtime.stop()

    async def navigate(
        self,
        session: object,
        url: str,
        navigation_policy: NavigationPolicy,
    ) -> str:
        browser_session = self._session(session)
        normalized = await self._validate_destination(url, navigation_policy)

        async def guard(route) -> None:
            request = route.request
            if request.is_navigation_request():
                await self._validate_destination(request.url, navigation_policy)
            await route.continue_()

        await browser_session.page.unroute("**/*")
        await browser_session.page.route("**/*", guard)
        await browser_session.page.goto(normalized, wait_until="domcontentloaded")
        final_url = await self._validate_destination(browser_session.page.url, navigation_policy)
        browser_session.navigation_sequence += 1
        return final_url

    async def observe(self, session: object) -> BrowserObservation:
        browser_session = self._session(session)
        observation_id = str(uuid.uuid4())
        visible_text = (await browser_session.page.locator("body").inner_text())[:12_000]
        title = await browser_session.page.title()
        raw_elements = await browser_session.page.locator(
            "button, a, input, select, textarea"
        ).evaluate_all(
            """
            nodes => nodes.slice(0, 100).map((node, index) => ({
                tag_name: node.tagName,
                role: node.getAttribute('role') ||
                    (node.tagName === 'INPUT'
                        ? ({button: 'button', submit: 'button', reset: 'button', checkbox: 'checkbox', radio: 'radio'})[node.type] || 'textbox'
                        : ({A: 'link', BUTTON: 'button', SELECT: 'combobox', TEXTAREA: 'textbox'})[node.tagName] || 'generic'),
                aria_label: node.getAttribute('aria-label'),
                label: node.labels?.[0]?.innerText || null,
                text: node.innerText || '',
                name: node.getAttribute('name') || '',
                placeholder: node.getAttribute('placeholder') || '',
                input_type: node.tagName === 'INPUT' ? node.type : '',
                button_value: node.tagName === 'INPUT' && ['button', 'submit', 'reset'].includes(node.type)
                    ? node.getAttribute('value') : null,
                form_name: node.form?.getAttribute('aria-label') || node.form?.getAttribute('name') || null,
                text_context: (node.parentElement?.innerText || '').slice(0, 500),
                index
            }))
            """
        )
        elements = tuple(_to_browser_element(observation_id, item) for item in raw_elements)
        return BrowserObservation(
            observation_id=observation_id,
            browser_session_id=browser_session.browser_session_id,
            url=browser_session.page.url,
            title=title or "Untitled page",
            visible_text=visible_text,
            elements=elements,
            observed_at=datetime.now(timezone.utc),
            navigation_sequence=browser_session.navigation_sequence,
            page_fingerprint=_fingerprint(browser_session.page.url, title, visible_text),
        )

    async def select(self, session: object, target: BrowserTarget) -> None:
        locator = await self._resolve_target(self._session(session), target)
        await locator.click()

    async def fill(self, session: object, target: BrowserTarget, value: str) -> None:
        locator = await self._resolve_target(self._session(session), target)
        await locator.fill(value)

    async def submit(self, session: object, target: BrowserTarget) -> None:
        locator = await self._resolve_target(self._session(session), target)
        await locator.click()

    async def _validate_destination(self, url: str, policy: NavigationPolicy) -> str:
        normalized = policy.validate(url)
        validate_addresses = getattr(policy, "validate_resolved_addresses", None)
        if callable(validate_addresses):
            host = urlsplit(normalized).hostname
            if host is None:
                raise ValueError("Navigation URL host is missing.")
            loop = asyncio.get_running_loop()
            records = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            validate_addresses(tuple(record[4][0] for record in records))
        return normalized

    async def _resolve_target(self, session: _PlaywrightBrowserSession, target: BrowserTarget):
        locator = session.page.get_by_role(target.role, name=target.accessible_name, exact=True)
        if await locator.count() != 1:
            raise ValueError("Browser target is missing or ambiguous on the current page.")
        return locator

    @staticmethod
    def _session(session: object) -> _PlaywrightBrowserSession:
        if not isinstance(session, _PlaywrightBrowserSession):
            raise ValueError("Playwright browser provider received an invalid session.")
        return session
