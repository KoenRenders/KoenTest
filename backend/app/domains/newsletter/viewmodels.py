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
    """`admin_nieuwsbrieven.html` and its fragment `_nb_lijst.html`: the kit's list page (#2123)."""

    letters: list[Any]
    # Per letter id, derived in the route (design-system §8.3).
    status_labels: dict[int, str]
    status_tones: dict[int, str]
    audience_labels: dict[int, str]
    progress: dict[int, Any]
    moments: dict[int, str]
    #: Per sent letter, what was counted (CR-37): opened and clicked as an indication.
    results: dict[int, Any]
    columns: list[dict[str, Any]]
    #: Alle, Concept, Wordt verstuurd and Verstuurd, each with its count.
    segments: list[dict[str, Any]]
    status: str = ""
    q: str = ""
    page: int = 1
    per_page: int = 50
    total: int = 0
    page_sizes: list[int] = field(default_factory=list)
    pager_url: str = ""
    empty_reason: str = ""
    csrf_token: str
    error: Optional[str] = None
    #: The fragment carries the toolbar's count and segment counts out-of-band.
    oob: bool = False
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AudienceLine:
    """One list a newsletter is sent to, as the send screen and the concept screen name it."""

    head: str
    sentence: str


@dataclass(frozen=True, kw_only=True)
class NewsletterHead:
    """What the record head of a draft shows (#2113): one description for the head of
    the page and for the head a save sends back out of band, so "Opgeslagen om" never
    says an older moment than the screen has."""

    letter: Any
    title: str
    #: The audience and when it was saved — each a plain text.
    facts: list[dict[str, str]]
    csrf_token: str
    #: The question of Verwijderen, in the edit-mode action bar (#2172).
    delete_confirm: str = ""


@dataclass(frozen=True, kw_only=True)
class NewsletterNoticeView(ViewModel):
    """`_nb_bewaard.html`: the line under the head — the answer of a command that
    leaves the page as it is (the test mail): why it was refused, or that it went."""

    error: Optional[str] = None
    notice: Optional[str] = None


@dataclass(frozen=True, kw_only=True)
class NewsletterComposeView(ViewModel):
    """`admin_nieuwsbrief.html` for a draft, with its fragments."""

    head: NewsletterHead
    letter: Any
    #: Whether the page opens in edit mode: asked for, or a letter that has no subject yet.
    editing: bool
    #: What the edit mode holds: the saved values.
    subject: str
    preview_text: str
    #: The letter's own audience as a code, to select the right option.
    audience: str
    #: `(code, label)` per audience on offer, in the code list's order.
    audience_options: list[tuple[str, str]]
    #: The saved audience in words, for the read mode ("" while there is none).
    audience_label: str
    #: Who each audience is, in the send screen's words (#1834): the lists and what
    #: they share, from the same function as that screen.
    audience_lines: list[AudienceLine]
    audience_overlap: str
    #: The list under *Eerdere deelnemers* (CR-36): shown only while that audience is
    #: the one chosen.
    participants_shown: bool
    participant_offered: list[Any]
    participant_lines: list[AudienceLine]
    participant_notes: list[str]
    #: The letter's text as the page editor's document, JSON text.
    body_json: str
    #: The page editor's configuration for the letter set, with the letter's featured
    #: activities for its activity dialog.
    editor_config: Any
    # Raakje (CR-05 §3.15): off when the back-office switch is off. Since #1562
    # the conversation stands in the Assistent's panel, not on this page.
    raakje_enabled: bool
    # What the letter is about, in three groups (#1562): per group its key, its
    # title, a hint, the chosen activities' facts and whether one more may join.
    choices: list[dict[str, Any]]
    #: `{id, label}` per FEATURED activity: the editor's activity dialog offers them.
    featured_options: list[dict[str, Any]]
    #: `(id, title)` of the site's pages a button of the letter may lead to.
    button_pages: list[tuple[int, str]]
    # How many whole meeting reports go along (CR-11 W13).
    report_count: int
    csrf_token: str
    error: Optional[str] = None
    notice: Optional[str] = None
    choices_error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class NewsletterParticipantsView(ViewModel):
    """`_nb_deelnemers.html` — the list of earlier activities to tick under the audience
    *Eerdere deelnemers* (CR-36, #2026): part of the record form, stored by its Opslaan.
    The fields are the compose view's, so the fragment and the page include the same
    partial."""

    letter: Any
    participants_shown: bool
    participant_offered: list[Any]


@dataclass(frozen=True, kw_only=True)
class NewsletterChoicesView(ViewModel):
    """`_nb_keuzes.html` — the three groups, after a choice changed."""

    letter: Any
    choices: list[dict[str, Any]]
    #: `{id, label}` per FEATURED activity: the editor's activity dialog offers them.
    featured_options: list[dict[str, Any]]
    report_count: int
    raakje_enabled: bool
    csrf_token: str
    choices_error: Optional[str] = None


@dataclass(frozen=True, kw_only=True)
class NewsletterPickerView(ViewModel):
    """`_nb_kiezer.html` — the activity picker, for one of the letter's three groups."""

    letter: Any
    #: `{id, name, date}` per activity offered.
    items: list[dict[str, Any]]
    q: str
    purpose: str
    csrf_token: str


@dataclass(frozen=True, kw_only=True)
class NewsletterConversationView(ViewModel):
    """`_nb_gesprek.html` — turns of the conversation with Raakje, for the
    Assistent's panel: all of them when the panel opens, the new one after a
    question. Per turn: `question`, `answer`, `failed` and, with a proposal, the
    proposal as the screen shows it (`drafting.display`) with its `fields`."""

    letter: Any
    turns: list[dict[str, Any]]


@dataclass(frozen=True, kw_only=True)
class NewsletterAppliedView(ViewModel):
    """`_nb_toegepast.html` — the answer to Toepassen: the final values for the
    form, or why the proposal could not be applied."""

    fields: list[dict[str, Any]]
    refusal: Optional[str] = None


@dataclass(frozen=True, kw_only=True)
class NewsletterArchiveView(ViewModel):
    """`admin_nieuwsbrief_archief.html` — a letter that is being or was sent."""

    letter: Any
    #: The letter's text as the mail shows it (the blocks built from today's data).
    body_html: str
    status_label: str
    status_tone: str
    audience_label: str
    #: The earlier activities a letter to *Eerdere deelnemers* went to, as a sentence
    #: ("" for any other audience; CR-36 R6).
    audience_activities: str
    progress: Any
    expected: str
    started: str
    finished: str
    deliveries: list[Any]
    #: `(code, label)` of the delivery statuses, for the filter. The badge
    #: per row reads its word and its tone from the filters (CR-12 phase 3).
    delivery_options: list[tuple[str, str]]
    moments: dict[int, str]
    #: What was counted for this letter (CR-37): the block *Resultaat* and its links.
    result: Any
    status_filter: str
    q: str
    csrf_token: str
    error: Optional[str] = None
    #: What the last action did (#1783): how many failed addresses are queued again.
    notice: str = ""
    #: The question "Opnieuw versturen" asks first; names how many addresses.
    resend_question: str = ""
    #: The words on that button: whom it sends to, with the number.
    resend_label: str = ""
    #: Which rows offer *Teruggekomen* (a sent one) and which take it back (#2188).
    markable: set[int] = field(default_factory=set)
    bounced: set[int] = field(default_factory=set)
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class NewsletterSendView(ViewModel):
    """`admin_nieuwsbrief_versturen.html` — the confirmation step."""

    letter: Any
    #: Who the letter goes to, said before the click (#1780): a head and a
    #: sentence per list it is sent to, and what the two lists share.
    audience_lines: list[AudienceLine]
    audience_overlap: str
    #: The send button, which names the audience: leden, abonnees, ontvangers.
    send_label: str
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
    """`admin_abonnees.html` and its fragment `_nb_abonnees.html`: the list page of
    the kit (#2109)."""

    subscribers: list[Any]
    counts: dict[str, int]
    #: The three figures of the title row (`ui.figures`).
    figures: list[dict[str, Any]]
    #: The status segments `{value, label}`, Alle first — from the code list, so the
    #: order is the list's and the value is the code (CR-12 phase 3). The badge per
    #: row uses the `code_label`/`tone` filters.
    segments: list[dict[str, str]]
    #: The kit table's columns and, per subscriber id, its row controls — the
    #: status decides here whether "Uitschrijven" stands, because a template
    #: does not compare codes (§B4.7) —
    #: "Uitschrijven" visible, "Verwijderen" behind ⋯ (#1925; Koen, 16
    #: October 2026, "7 ja").
    columns: list[dict]
    row_controls: dict[int, dict]
    source_labels: dict[int, str]
    moments: dict[int, str]
    q: str
    status: str
    sort: str
    sort_options: list[tuple[str, str]]
    page: int
    per_page: int
    total: int
    page_sizes: list[int]
    pager_url: str
    empty_reason: str
    csrf_token: str
    error: Optional[str] = None
    notice: Optional[str] = None
    oob: bool = False
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class SubscriberNewView(ViewModel):
    """`admin_abonnee_nieuw.html` — the page "+ Adres" opens."""

    csrf_token: str
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
    #: Where the unsubscribe button posts, when it is not the page of a token (a
    #: participant's signed link, CR-36).
    action: str = ""
    #: The page after "Toch opnieuw": it says what that means from now on.
    resubscribed: bool = False
    error: Optional[str] = None
    site: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> dict[str, Any]:
        context = super().as_context()
        context.pop("site", None)
        context.update(self.site)
        return context
