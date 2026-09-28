"""The short date is written in one place (#1242).

`strftime("%d-%m-%Y")` stood 22 times by hand in templates and modules. Since
#1242 every short date comes from `app.i18n.short_date` (the `kortedatum`
filter) and every short date with a time from `short_datetime`. This gate keeps
a 23rd from appearing: a list next to a source drifts, as the number formats of
the report panel did (#875).

The gate counts before it judges. It must find the one allowed `strftime` in
`app/i18n.py` — a scan that finds nothing because its pattern broke would
otherwise read as green.

Broken on purpose (27 September 2026): `a.sort_date|kortedatum` in
`_aa_kaarten.html` turned back into `a.sort_date.strftime("%d-%m-%Y")` → the
gate failed naming `app/domains/activities/templates/_aa_kaarten.html:15`. And
the pattern broken (`%d/%m-%Y`) → it failed on "does not even find the one
allowed strftime", instead of passing everything.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

#: A formatting call with the short date, in Python or Jinja. Parsing
#: (`strptime`, a tuple of accepted input formats) is not formatting and is
#: allowed: the member report reads dates people typed in several ways.
_HAND_WRITTEN = re.compile(r"""strftime\(\s*["']%d-%m-%Y""")

#: The one place that may spell it.
_SOURCE = APP / "i18n.py"


def _hits() -> list[str]:
    found = []
    for path in sorted(APP.rglob("*")):
        if path.suffix not in (".py", ".html") or not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _HAND_WRITTEN.search(line):
                found.append(f"{path.relative_to(APP.parent)}:{number}")
    return found


def test_the_short_date_is_formatted_in_one_place():
    hits = _hits()
    source = [h for h in hits if h.startswith(f"{_SOURCE.relative_to(APP.parent)}:")]
    assert source, (
        "the gate does not even find the one allowed strftime in app/i18n.py — "
        "its pattern or its path is broken, so it would pass anything"
    )
    others = [h for h in hits if h not in source]
    assert not others, (
        "a short date written by hand; use the `kortedatum` or `short_datetime` "
        f"filter in a template, or `app.i18n.short_date` / `short_datetime` in Python: {others}"
    )


def test_short_datetime_reads_as_the_hand_written_format_did():
    """The replacement changes nothing on screen: the same text as the old
    `strftime("%d-%m-%Y %H:%M")`, for a morning and an evening, with and
    without a time zone."""
    from datetime import datetime, timezone

    from app.i18n import short_datetime

    for moment in (datetime(2026, 9, 7, 8, 5), datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)):
        assert short_datetime(moment) == moment.strftime("%d-%m-%Y %H:%M")
    assert short_datetime(None) == ""


def test_short_date_reads_as_the_hand_written_format_did():
    """Same for the date alone, on a date and on a datetime — the templates
    handed it both (a start date, a registration moment)."""
    from datetime import date, datetime

    from app.i18n import short_date

    for day in (date(2026, 1, 5), datetime(2026, 11, 30, 18, 0)):
        assert short_date(day) == day.strftime("%d-%m-%Y")
