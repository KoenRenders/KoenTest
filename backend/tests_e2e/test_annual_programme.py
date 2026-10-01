"""E2E: the report "Jaarprogramma" at 390 px (#1428, part B; #1439).

Measured:
- the report opens from its saved row and lists a draft activity of three
  dates ONCE (#1439), with "Concept" in it and its three dates in one cell;
- the nine columns scroll inside their own box, within the width;
- the page is no wider than with an existing report. It is NOT 390: the panel's
  layout switch (Tabel · Gestapeld · Lijst) makes every report page 522 px wide
  at 390, "Betalingen en vorderingen" included. That is the panel, not this
  report, and it is reported rather than changed here.

Screenshots go outside the repo.
"""

import os
import secrets
import sys
from datetime import date, time

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1428"
PHONE = {"width": 390, "height": 900}
WIDTH = "() => [document.documentElement.scrollWidth, innerWidth]"

_ROWS = """(name) => {
  const rows = [...document.querySelectorAll('tr')].filter(r => r.textContent.includes(name));
  const table = rows.length ? rows[0].closest('table') : null;
  const box = table ? table.parentElement : null;
  const cells = rows.length ? [...rows[0].querySelectorAll('td')].map(c => c.textContent.trim()) : [];
  const dates = cells.map(c => c.split(' · ').length).reduce((a, b) => Math.max(a, b), 0);
  return {rows: rows.length, concept: rows.filter(r => r.textContent.includes('Concept')).length, dates,
          table: table && Math.round(table.getBoundingClientRect().width),
          box: box && [Math.round(box.getBoundingClientRect().width), getComputedStyle(box).overflowX]};
}"""


def _situation() -> tuple[int, int, str]:
    """A draft course of three evenings this year, the programme's report id, and
    the id of an existing report to compare the page width with."""
    from sqlalchemy import text

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate, ActivityStatus

    db = SessionLocal()
    try:
        year = db.execute(text("SELECT CURRENT_DATE")).scalar().year
        name = f"Kookcursus {secrets.token_hex(2)}"
        activity = Activity(name=name, status=ActivityStatus.DRAFT, target_audience="women")
        db.add(activity)
        db.flush()
        for month in (1, 2, 3):
            db.add(
                ActivityDate(
                    activity_id=activity.id,
                    start_date=date(year, month, 10),
                    start_time=time(19, 30),
                )
            )
        report_id = db.execute(
            text(
                "SELECT id FROM reporting.saved_reports WHERE builtin_key = 'annual_programme' "
                "AND tenant_id = :t AND deleted_at IS NULL"
            ),
            {"t": activity.tenant_id},
        ).scalar_one()
        payments_id = db.execute(
            text(
                "SELECT id FROM reporting.saved_reports WHERE builtin_key = 'payments_list' "
                "AND tenant_id = :t AND deleted_at IS NULL"
            ),
            {"t": activity.tenant_id},
        ).scalar_one()
        db.commit()
        return report_id, payments_id, name
    finally:
        db.close()


@pytest.fixture(scope="module")
def phone():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    report_id, payments_id, name = _situation()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = b.new_page(base_url=BASE, viewport=PHONE)
        login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL))
        yield page, report_id, payments_id, name
        b.close()


def test_the_programme_lists_every_date_of_a_draft(phone):
    page, report_id, payments_id, name = phone
    page.goto(f"/admin/rapporten/{payments_id}")
    pagina_klaar(page)
    existing = page.evaluate(WIDTH)
    page.goto(f"/admin/rapporten/{report_id}")
    pagina_klaar(page)
    page.get_by_text(name).first.wait_for()
    m = page.evaluate(_ROWS, name)
    width = page.evaluate(WIDTH)
    print("MEASURE programme", m, "page", width, "existing report", existing)
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/390-jaarprogramma.png", full_page=True)
    assert m["rows"] == 1 and m["concept"] == 1, m
    assert m["dates"] == 3, m
    assert m["box"][0] <= 390 and m["box"][1] in ("auto", "scroll"), m
    assert m["table"] > m["box"][0], "the columns are wider than the box, so it scrolls"
    assert width[0] <= existing[0], f"wider than an existing report: {width} vs {existing}"
