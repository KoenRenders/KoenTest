"""View-models of the meeting screens (CR-09, #258).

What each screen gets from its route, typed, in one place — so a wrong or
forgotten key is an error in the route instead of an empty box on the screen,
and `tests/test_template_variables_gate.py` can prove statically that the
templates ask for nothing that is not promised here.
"""
from dataclasses import dataclass, field
from typing import Any, Optional

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class MeetingListView(ViewModel):
    """`admin_vergaderingen.html` and its fragment `_vg_lijst.html`."""

    meetings: list[Any]
    # Per meeting id: the badge label and tone of its status. Derived in the
    # route, because a template that derives state is a second place where the
    # rule lives (design-system §8.3).
    status_labels: dict[int, str]
    status_tones: dict[int, str]
    dates: dict[int, str]
    circle_size: int
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class MeetingNewView(ViewModel):
    """`admin_vergadering_nieuw.html` — één datum volstaat om te beginnen."""

    suggested_date: str
    suggested_time: str
    suggested_location: str
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class MeetingDocumentView(ViewModel):
    """`admin_vergadering.html` and its fragment `_vg_document.html`.

    One view-model for the agenda and the report: they are the same document in
    two statuses (§3.23), so two view-models would be two descriptions of one
    screen — and they would drift.
    """

    meeting: Any
    title: str
    status_label: str
    status_tone: str
    sections: list[Any]
    # The circle, with who is ticked present or excused.
    circle: list[Any]
    attendance: dict[int, str]
    # The members header, following the renewal cycle (§3.20).
    standing: Any
    # The picker behind "Punt toevoegen": which section it targets, and what it
    # offers. Empty unless the picker is open, so one template covers both.
    picker_section_id: Optional[int]
    picker_options: list[Any]
    picker_query: str
    attachments: list[Any]
    sent_pdfs: list[Any]
    editable: bool
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class MeetingSendView(ViewModel):
    """`admin_vergadering_verstuur.html` — the deliberate stop before sending."""

    meeting: Any
    kind: str                      # "agenda" | "report"
    kind_label: str
    subject: str
    body: str
    recipients: Any
    extra_recipients: list[Any]
    attachments: list[Any]
    pdf_filename: str
    reply_to: str
    already_sent_at: Optional[Any]
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class MeetingCircleView(ViewModel):
    """`admin_vergaderkring.html` — who receives agenda and report.

    Its own screen because the circle is master data with its own lifetime: it
    outlives every single meeting, and it holds people who are not members.
    """

    circle: list[Any]
    candidates: list[Any]
    query: str
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)
