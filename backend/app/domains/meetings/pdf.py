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
from pathlib import Path

from weasyprint import HTML

from app.i18n import _

# Dutch month names — the PDF is read by board members, so it follows the UI
# language, not the server locale (which is C in the container).
MONTHS = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)
WEEKDAYS = ("maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag")


def long_date(day: date | None) -> str:
    """`donderdag 1 oktober 2026` — how the board writes a date."""
    if day is None:
        return ""
    return f"{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]} {day.year}"


def clock(moment) -> str:
    """`20u` of `20u30` — zoals het bestuur een uur schrijft.

    Hier en niet in de service, naast `long_date` en `short_date`: het is
    datum-opmaak, en drie plaatsen die elk hun eigen uur opmaken is precies hoe
    de ene op een dag "20:00" gaat tonen en de andere "20u".
    """
    if moment is None:
        return ""
    return f"{moment.hour}u" + (f"{moment.minute:02d}" if moment.minute else "")


def moment(start_date, start_time=None, end_date=None, end_time=None) -> str:
    """When one date row of an activity runs, as a meeting point reads it (#1335).

    `zaterdag 1 mei 2026 14u – zondag 3 mei 2026 17u`, or `donderdag 20 augustus
    2026 19u – 22u` when it falls on one day. What is missing is left out, and so
    is the dash that would introduce it: an end time without a start time says
    nothing on a single day.

    The dates come from `app.i18n.long_date`, the source of the `langedatum`
    filter (#1242); the hours from `clock`, as everywhere in a meeting.
    """
    from app.i18n import long_date as long_date_i18n

    if start_date is None:
        return ""
    begin = f"{long_date_i18n(start_date)} {clock(start_time)}".strip()
    if end_date and end_date != start_date:
        end = f"{long_date_i18n(end_date)} {clock(end_time)}".strip()
        return f"{begin} – {end}"
    if start_time and end_time:
        return f"{begin} – {clock(end_time)}"
    return begin


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


# Waar de lettertypes staan. De PDF laadt ze rechtstreeks van schijf: WeasyPrint
# rendert los van de webserver, dus een URL zou niets opleveren — en een verslag
# dat bij het genereren het net op moet, komt op een dag zonder letters uit de
# printer.
STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


def render(*, context: dict, base_url: str | None = None) -> bytes:
    """Render the meeting document to PDF bytes.

    Takes a ready-made context rather than the session: the PDF shows exactly
    what the screen shows, and building that twice is how the two drift apart.
    """
    from app.ui import templates

    html = templates.env.get_template("meeting_pdf.html").render(**context)
    buffer = BytesIO()
    HTML(string=html, base_url=base_url or f"{STATIC_DIR}/").write_pdf(buffer)
    return buffer.getvalue()
