"""View-models of the newsletter screens (CR-05, #984).

What each screen gets from its route, typed, in one place, so
`tests/test_template_variables_gate.py` can prove the templates ask for
nothing that is not promised here.
"""
from dataclasses import dataclass, field
from typing import Any, Optional

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class NewsletterListView(ViewModel):
    """`admin_nieuwsbrieven.html` and its fragment `_nb_lijst.html`."""

    letters: list[Any]
    # Per letter id, derived in the route (design-system §8.3).
    status_labels: dict[int, str]
    status_tones: dict[int, str]
    audience_labels: dict[int, str]
    progress: dict[int, Any]
    moments: dict[int, str]
    q: str = ""
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class NewsletterComposeView(ViewModel):
    """`admin_nieuwsbrief.html` for a draft, with its fragments."""

    letter: Any
    counts: Any
    audience_options: list[tuple[str, str, str]]
    saved_at: str
    # The reminder of CR-05 §3.6: imported addresses that never got a letter.
    first_letter_after_import: bool
    # Raakje (CR-05 §3.15): off when the back-office switch is off.
    raakje_enabled: bool
    chosen_activities: list[Any]
    report_points: list[Any]
    ticked_points: list[int]
    messages: list[Any]
    csrf_token: str
    error: Optional[str] = None
    notice: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class NewsletterPickerView(ViewModel):
    """`_nb_kiezer.html` — the activity picker, for inserting or for Raakje."""

    letter: Any
    spans: list[Any]
    dates: dict[int, str]
    q: str
    purpose: str
    csrf_token: str


@dataclass(frozen=True, kw_only=True)
class NewsletterArchiveView(ViewModel):
    """`admin_nieuwsbrief_archief.html` — a letter that is being or was sent."""

    letter: Any
    status_label: str
    status_tone: str
    audience_label: str
    progress: Any
    expected: str
    started: str
    finished: str
    deliveries: list[Any]
    delivery_labels: dict[str, str]
    delivery_tones: dict[str, str]
    moments: dict[int, str]
    status_filter: str
    q: str
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class NewsletterSendView(ViewModel):
    """`admin_nieuwsbrief_versturen.html` — the confirmation step."""

    letter: Any
    audience_label: str
    recipient_count: int
    days: int
    daily_cap: int
    reply_to_sender: str
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class SubscriberListView(ViewModel):
    """`admin_abonnees.html` and its fragment `_nb_abonnees.html`."""

    subscribers: list[Any]
    counts: dict[str, int]
    status_labels: dict[str, str]
    status_tones: dict[str, str]
    source_labels: dict[int, str]
    moments: dict[int, str]
    q: str
    status: str
    csrf_token: str
    error: Optional[str] = None
    notice: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class SubscriberImportView(ViewModel):
    """`admin_abonnees_import.html` — upload, then the preview."""

    preview: Any
    text: str
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class NewsletterSettingsView(ViewModel):
    """`admin_nieuwsbrief_instellingen.html`."""

    house_style: str
    daily_cap: int
    daily_cap_default: int
    csrf_token: str
    notice: Optional[str] = None
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class PublicNewsletterView(ViewModel):
    """The public pages: signup, confirm, unsubscribe (mobile first)."""

    state: str
    email: str = ""
    token: str = ""
    error: Optional[str] = None
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context
