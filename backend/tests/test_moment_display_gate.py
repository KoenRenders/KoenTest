"""Refuses a moment shown without the one conversion to Brussels · hard · since #1976.

A moment shown to a person is shown in the association's time, and the
conversion stands in one place: `app.i18n.local_moment`, behind the filters
`short_datetime`, `kortedatum`, `langedatum`, `datumzonderjaar` and `clock_time`,
and `app.i18n.moment_text` for an export with a shape of its own. Before #1976
the newsletter converted on its own and the rest of the back office showed UTC.
Three ways a moment gets past that place, each refused here:

- **a clock time formatted by hand** — `strftime` with `%H`, outside
  `app/i18n.py`, on anything but a time of day (a `*_time` column, or a value
  named below with its reason). A `time` the board typed has no zone and is
  shown as typed; a moment is not a `time`;
- **a screen that converts on its own** — `astimezone` or `ZoneInfo` in a
  screen module (`ui.py`, `admin_ui.py`, `*_ui.py`, a view-model) or a template;
- **a template that takes the day of a moment itself** — `.date()` in a
  template is the UTC day between midnight and 02:00; the date filters take the
  moment and give its day in Brussels.

The gate counts before it judges: it must find the time-of-day `strftime`s it
allows, or its pattern broke and it would pass anything.

Broken on purpose (15 October 2026, each by adding a line, each put back):
- `{{ peilmoment.strftime("%H:%M") }}` in `admin_dashboard.html` → the first
  test failed naming `app/ui/templates/admin_dashboard.html:32`;
- a line with `.astimezone(BELGIUM)` in `chatbot/admin_ui.py` → the second
  failed naming `app/domains/chatbot/admin_ui.py:95`;
- `{{ r.last_run_at.date()|langedatum }}` in `_rp_kaarten.html` → the third
  failed naming `app/domains/reporting/templates/_rp_kaarten.html:29`.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests._bestanden import is_app_test

APP = Path(__file__).resolve().parents[1] / "app"

#: Every `strftime` that writes an hour.
_HOUR = re.compile(r"""\.strftime\(\s*["'][^"']*%H""")
#: The name it is called on, when that is a plain name (not a call's result).
_NAME_AT_END = re.compile(r"(\w+)\s*$")

#: A value that is a time of day but does not end in `_time`, with its reason.
_TIME_OF_DAY = {
    ("app/domains/activities/proposer.py", "value"): "`_hhmm(value: Optional[time])`",
}

_CONVERTS = re.compile(r"\.astimezone\(|ZoneInfo\(")
_DAY_IN_TEMPLATE = re.compile(r"\.date\(\)")


def _files(suffixes: tuple[str, ...]):
    for path in sorted(APP.rglob("*")):
        if path.suffix in suffixes and path.is_file() and not is_app_test(path):
            yield path


def _lines(path: Path):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        yield number, line


def _where(path: Path, number: int) -> str:
    return f"{path.relative_to(APP.parent)}:{number}"


def _is_screen(path: Path) -> bool:
    name = path.name
    return (
        path.suffix == ".html"
        or name in ("ui.py", "admin_ui.py")
        or name.endswith("_ui.py")
        or name.startswith("viewmodels")
    )


def test_a_clock_time_is_written_by_hand_only_for_a_time_of_day():
    allowed, refused = [], []
    for path in _files((".py", ".html")):
        if path == APP / "i18n.py":
            continue
        relative = str(path.relative_to(APP.parent))
        for number, line in _lines(path):
            for match in _HOUR.finditer(line):
                before = _NAME_AT_END.search(line[: match.start()])
                name = before.group(1) if before else ""
                if name.endswith("_time") or (relative, name) in _TIME_OF_DAY:
                    allowed.append(_where(path, number))
                else:
                    refused.append(_where(path, number))
    assert len(allowed) >= 5, (
        f"the gate finds only {allowed} — the start and end times of the activity "
        "forms are at least five; its pattern or its path is broken"
    )
    assert not refused, (
        "a moment's time formatted by hand, so not in Brussels: use the "
        "`short_datetime` or `clock_time` filter, `app.i18n.short_datetime`, or "
        f"`app.i18n.moment_text` for an export: {refused}"
    )


def test_a_screen_never_converts_a_moment_itself():
    screens = [p for p in _files((".py", ".html")) if _is_screen(p)]
    assert len(screens) > 50, f"the gate finds only {len(screens)} screen files"
    refused = [
        _where(path, number)
        for path in screens
        for number, line in _lines(path)
        if _CONVERTS.search(line)
    ]
    assert not refused, (
        "a screen converts a moment itself; hand it to the filter as it is "
        f"(`app.i18n.local_moment` converts, #1976): {refused}"
    )


def test_a_template_never_takes_the_day_of_a_moment_itself():
    templates = list(_files((".html",)))
    assert len(templates) > 100, f"the gate finds only {len(templates)} templates"
    refused = [
        _where(path, number)
        for path in templates
        for number, line in _lines(path)
        if _DAY_IN_TEMPLATE.search(line)
    ]
    assert not refused, (
        "a template takes a moment's day itself — the UTC day until 02:00; give "
        f"the moment to `kortedatum` or `langedatum`: {refused}"
    )
