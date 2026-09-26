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
    #: `(code, label, count, hint)` — the code is the radio value, so the
    #: template never renders an enum member into an attribute.
    audience_options: list[tuple[str, str, str, str]]
    #: The letter's own audience as a code, to tick the right radio.
    audience: str
    saved_at: str
    # Raakje (CR-05 §3.15): off when the back-office switch is off.
    raakje_enabled: bool
    # What Raakje writes about (Koen, 17 September 2026): past and coming
    # activities, and whole meeting reports to tick.
    past_activities: list[Any]
    coming_activities: list[Any]
    reports: list[tuple[int, str]]
    ticked_reports: list[int]
    # The conversation as turns (question, answer), newest turn first.
    turns: list[Any]
    # Per message id: is this the author's own line, or Raakje's answer? The
    # screen draws two different bubbles; it does not compare codes (§B4.7).
    by_author: dict[int, bool]
    # Per Raakje message id: the proposal as the screen shows it.
    proposals: dict[int, Any]
    csrf_token: str
    error: Optional[str] = None
    notice: Optional[str] = None
    raakje_error: Optional[str] = None
    # After "Toepassen": the HTML the editor takes over, and where it goes.
    apply_html: str = ""
    apply_placement: str = ""
    apply_range: str = ""
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class NewsletterPickerView(ViewModel):
    """`_nb_kiezer.html` — the activity picker, for inserting or for Raakje."""

    letter: Any
    spans: list[Any]
    dates: dict[int, str]
    q: str
    purpose: str
    # Which boxes start ticked — only the calendar uses this.
    ticked: list[int]
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
    #: `(code, label)` of the delivery statuses, for the filter. The badge
    #: per row reads its word and its tone from the filters (CR-12 phase 3).
    delivery_options: list[tuple[str, str]]
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
    # A placeholder is still in the letter: the send button is not offered.
    blocked: bool
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class SubscriberListView(ViewModel):
    """`admin_abonnees.html` and its fragment `_nb_abonnees.html`."""

    subscribers: list[Any]
    counts: dict[str, int]
    #: `(code, label)` of the active statuses, for the filter — from the code
    #: list, so the order is the list's and the option value is the code
    #: (CR-12 phase 3). The badge per row uses the `code_label`/`tone` filters.
    status_options: list[tuple[str, str]]
    #: Per subscriber id: may this address still be unsubscribed? Derived
    #: here, because a template does not compare codes (§B4.7).
    unsubscribable: dict[int, bool]
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
