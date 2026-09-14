"""The agenda and the report as a PDF (CR-09 §3.16, §3.8).

WeasyPrint renders HTML/CSS in-process, so the document is a Jinja template like
every screen — the same macros, the same brand colours, one place to change how a
meeting looks. Europe First: open source, self-hosted, maintained by
CourtBouillon (FR); the alternatives weighed were ReportLab (programmatic layout,
more code per layout change) and headless Chromium (heavy in the image).

The import is deliberately at module import time, not inside the function: the
build-time import check (`check_imports.py`) then breaks the Docker build when the
Pango/Cairo system packages are missing, instead of the first PDF failing in
production months later.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO

from weasyprint import HTML

from app.i18n import _

# Dutch month names — the PDF is read by board members, so it follows the UI
# language, not the server locale (which is C in the container).
MONTHS = ("januari", "februari", "maart", "april", "mei", "juni", "juli",
          "augustus", "september", "oktober", "november", "december")
WEEKDAYS = ("maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
            "zaterdag", "zondag")


def long_date(day: date | None) -> str:
    """`donderdag 1 oktober 2026` — how the board writes a date."""
    if day is None:
        return ""
    return f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]} {day.year}"


def short_date(day: date | None) -> str:
    """`1 oktober` — inside an item line, where the year is already known."""
    if day is None:
        return ""
    return f"{day.day} {MONTHS[day.month - 1]}"


def filename_for(meeting, *, kind: str) -> str:
    """`verslag-2026-10-01.pdf`. Sorts chronologically in a mailbox, which is
    where these files spend their lives."""
    stem = _("agenda") if kind == "agenda" else _("verslag")
    return f"{stem}-{meeting.meeting_date.isoformat()}.pdf"


def render(*, context: dict, base_url: str | None = None) -> bytes:
    """Render the meeting document to PDF bytes.

    Takes a ready-made context rather than the session: the PDF shows exactly
    what the screen shows, and building that twice is how the two drift apart.
    """
    from app.ui import templates

    html = templates.env.get_template("meeting_pdf.html").render(**context)
    buffer = BytesIO()
    HTML(string=html, base_url=base_url).write_pdf(buffer)
    return buffer.getvalue()
