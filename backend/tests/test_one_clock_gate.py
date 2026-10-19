"""Refuses a second clock: no `date.today()` and no database `CURRENT_DATE` in the application · hard · since #2156.

"Today" belongs to the tenant (`mdm.tenants.time_zone`). The application asks
`kernel.clock` (`belgian_today`, `belgian_day`, `belgian_now`); SQL asks
`mdm.tenant_today()` / `mdm.tenant_day()`. A `date.today()` answers in the host's zone and
a `CURRENT_DATE` in the database's (UTC), so either is a day that can differ from the
tenant's — the disagreement that made the dashboard and the member list, or a saved report
and its button, fall on different days between midnight in Belgium and midnight UTC.

The reporting views are checked against the live schema in
`app/domains/mdm/tests/test_tenant_time_zone_2156.py`; this gate reads the sources of `app/`
(migrations are history and stay as they are).

Proven red, additively (put back): a line `today = date.today()` added to
`domains/payment/service.py` → the first test names the file and the line; the gate's own
function is run on strings below.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

#: The clock itself says why it exists; its docstring names the host's `date.today()`.
EXEMPT = {"kernel/clock.py"}

FORBIDDEN = re.compile(
    r"\bdate\.today\(\)|\bdatetime\.now\(\)\.date\(\)|\bdatetime\.today\(\)"
    r"|\bCURRENT_DATE\b|\bcurrent_date\b|\bnow\(\)::date\b|\bCURRENT_TIMESTAMP\b"
)


def violations(text: str) -> list[tuple[int, str]]:
    """The lines of one source that ask a clock other than the tenant's, comments and
    docstring prose aside: only a line that is code or an SQL string counts, so a line
    starting with `#` is skipped."""
    return [
        (number, line.strip())
        for number, line in enumerate(text.splitlines(), 1)
        if FORBIDDEN.search(line) and not line.lstrip().startswith("#")
    ]


def test_no_source_of_the_application_asks_another_clock():
    sources = [
        path
        for path in sorted(APP.rglob("*.py"))
        if "/tests/" not in path.as_posix()
        and path.relative_to(APP).as_posix() not in EXEMPT
        and "alembic" not in path.as_posix()
    ]
    assert len(sources) > 300, f"the scan found only {len(sources)} sources — it is blind"
    found = [
        f"{path.relative_to(APP)}:{number}: {line[:100]}"
        for path in sources
        for number, line in violations(path.read_text())
    ]
    assert not found, (
        "ask `kernel.clock` (the tenant's day), or `mdm.tenant_today()` in SQL:\n  "
        + "\n  ".join(found)
    )


def test_the_gate_sees_each_form_and_skips_a_comment():
    for bad in (
        "today = date.today()",
        "x = datetime.now().date()",
        "SELECT CURRENT_DATE - created_at::date",
        "WHERE d >= current_date",
        "SELECT now()::date",
    ):
        assert violations(bad), bad
    assert not violations("# date.today() answers in the host's zone")
    assert not violations("today = belgian_today()")
