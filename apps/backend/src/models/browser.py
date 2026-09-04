from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


MAX_BROWSER_VISIBLE_TEXT_CHARACTERS = 12_000
MAX_BROWSER_ELEMENTS = 100
MAX_BROWSER_ELEMENT_CONTEXT_CHARACTERS = 500


def _required_text(value: str, field_name: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    if len(value) > maximum:
        raise ValueError(f"{field_name} exceeds its maximum length.")
    return value


@dataclass(frozen=True)
class BrowserElement:
    """A bounded semantic element captured within one observation."""

    element_ref: str
    role: str
    accessible_name: str
    semantic_fingerprint: str
    label: str | None = None
    form_name: str | None = None
    text_context: str = ""
    is_sensitive: bool = False

    def __post_init__(self) -> None:
        _required_text(self.element_ref, "element_ref")
        _required_text(self.role, "role")
        _required_text(self.accessible_name, "accessible_name")
        _required_text(self.semantic_fingerprint, "semantic_fingerprint")
        if self.label is not None:
            _required_text(self.label, "label")
        if self.form_name is not None:
            _required_text(self.form_name, "form_name")
        if not isinstance(self.text_context, str):
            raise ValueError("text_context must be a string.")
        if len(self.text_context) > MAX_BROWSER_ELEMENT_CONTEXT_CHARACTERS:
            raise ValueError("text_context exceeds its maximum length.")
        if not isinstance(self.is_sensitive, bool):
            raise ValueError("is_sensitive must be a boolean.")

    def to_payload(self) -> dict[str, str | None]:
        return {
            "element_ref": self.element_ref,
            "role": self.role,
            "accessible_name": self.accessible_name,
            "semantic_fingerprint": self.semantic_fingerprint,
            "label": self.label,
            "form_name": self.form_name,
            "text_context": self.text_context,
            "is_sensitive": self.is_sensitive,
        }


@dataclass(frozen=True)
class BrowserObservation:
    """Structured untrusted page facts, bounded before planner use or persistence."""

    observation_id: str
    browser_session_id: str
    url: str
    title: str
    visible_text: str
    elements: tuple[BrowserElement, ...]
    observed_at: datetime
    navigation_sequence: int
    page_fingerprint: str

    def __post_init__(self) -> None:
        _required_text(self.observation_id, "observation_id")
        _required_text(self.browser_session_id, "browser_session_id")
        _required_text(self.url, "url", maximum=2_048)
        _required_text(self.title, "title", maximum=1_024)
        if not isinstance(self.visible_text, str):
            raise ValueError("visible_text must be a string.")
        if len(self.visible_text) > MAX_BROWSER_VISIBLE_TEXT_CHARACTERS:
            raise ValueError("visible_text exceeds its maximum length.")
        if not isinstance(self.elements, tuple):
            raise ValueError("elements must be a tuple of BrowserElement values.")
        if len(self.elements) > MAX_BROWSER_ELEMENTS:
            raise ValueError("elements exceeds its maximum count.")
        if not all(isinstance(element, BrowserElement) for element in self.elements):
            raise ValueError("elements must contain BrowserElement values.")
        if not isinstance(self.observed_at, datetime):
            raise ValueError("observed_at must be a datetime.")
        if not isinstance(self.navigation_sequence, int) or self.navigation_sequence < 0:
            raise ValueError("navigation_sequence must be a non-negative integer.")
        _required_text(self.page_fingerprint, "page_fingerprint")

    def to_payload(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "browser_session_id": self.browser_session_id,
            "url": self.url,
            "title": self.title,
            "visible_text": self.visible_text,
            "elements": [element.to_payload() for element in self.elements],
            "observed_at": self.observed_at.isoformat(),
            "navigation_sequence": self.navigation_sequence,
            "page_fingerprint": self.page_fingerprint,
        }


@dataclass(frozen=True)
class BrowserTarget:
    """Durable semantic targeting facts, never a durable DOM-node handle."""

    browser_session_id: str
    observation_id: str
    element_ref: str
    observed_url: str
    role: str
    accessible_name: str
    label: str | None
    form_name: str | None
    text_context: str
    semantic_fingerprint: str
    is_sensitive: bool = False

    def __post_init__(self) -> None:
        _required_text(self.browser_session_id, "browser_session_id")
        _required_text(self.observation_id, "observation_id")
        _required_text(self.element_ref, "element_ref")
        _required_text(self.observed_url, "observed_url", maximum=2_048)
        _required_text(self.role, "role")
        _required_text(self.accessible_name, "accessible_name")
        _required_text(self.semantic_fingerprint, "semantic_fingerprint")
        if self.label is not None:
            _required_text(self.label, "label")
        if self.form_name is not None:
            _required_text(self.form_name, "form_name")
        if not isinstance(self.text_context, str):
            raise ValueError("text_context must be a string.")
        if len(self.text_context) > MAX_BROWSER_ELEMENT_CONTEXT_CHARACTERS:
            raise ValueError("text_context exceeds its maximum length.")
        if not isinstance(self.is_sensitive, bool):
            raise ValueError("is_sensitive must be a boolean.")

    def to_payload(self) -> dict[str, str | None]:
        return {
            "browser_session_id": self.browser_session_id,
            "observation_id": self.observation_id,
            "element_ref": self.element_ref,
            "observed_url": self.observed_url,
            "role": self.role,
            "accessible_name": self.accessible_name,
            "label": self.label,
            "form_name": self.form_name,
            "text_context": self.text_context,
            "semantic_fingerprint": self.semantic_fingerprint,
            "is_sensitive": self.is_sensitive,
        }

    @classmethod
    def from_payload(cls, payload: object) -> "BrowserTarget":
        if not isinstance(payload, dict):
            raise ValueError("Browser target must be a JSON object.")
        required = {
            "browser_session_id",
            "observation_id",
            "element_ref",
            "observed_url",
            "role",
            "accessible_name",
            "label",
            "form_name",
            "text_context",
            "semantic_fingerprint",
            "is_sensitive",
        }
        if set(payload) != required:
            raise ValueError("Browser target must contain the complete semantic target.")
        try:
            return cls(**payload)
        except TypeError as exc:
            raise ValueError("Browser target has invalid fields.") from exc
