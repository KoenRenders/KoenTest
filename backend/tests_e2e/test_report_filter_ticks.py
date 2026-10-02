"""E2E: the ticks of a report filter, at 390 and 1280 px (#1445).

Measured on the shipped "Jaarprogramma", which filters on "Dit jaar":
- the filter block stays within the width, and so does the box of ticks;
- every tick row is at least 44 px high, the whole row a click target;
- #1453: without scrolling the box, the rows of this year and next year stand
  inside its visible part, right under "Dit jaar" — measured on geometry, since
  Playwright would scroll to a row itself;
- a real click on next year, in the browser, re-renders the panel with BOTH
  "Dit jaar" and next year ticked, and both years' activities in the table —
  the request htmx builds from the form, not one a test wrote by hand.

Screenshots go outside the repo.
"""

import os
import secrets
import sys
from datetime import date

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1445"

_MEASURE = """() => {
  const r = e => { const b = e.getBoundingClientRect(); return {x: Math.round(b.x), right: Math.round(b.right), h: Math.round(b.height)}; };
  const block = document.querySelector('#rp-filters');
  const box = block && block.querySelector('fieldset');
  const rows = box ? [...box.querySelectorAll('label')] : [];
  return {width: [document.documentElement.scrollWidth, innerWidth],
          block: block && r(block), box: box && r(box),
          rows: rows.map(l => ({text: l.textContent.trim(), h: r(l).h,
                                checked: l.querySelector('input').checked}))};
}"""


def _situation() -> tuple[int, int, str]:
    """An activity this year and one next year; the programme's report id."""
    from sqlalchemy import text

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate

    db = SessionLocal()
    try:
        year = db.execute(text("SELECT CURRENT_DATE")).scalar().year
        mark = secrets.token_hex(2)
        for y in (year, year + 1):
            activity = Activity(name=f"Vinkje {y} {mark}")
            db.add(activity)
            db.flush()
            db.add(ActivityDate(activity_id=activity.id, start_date=date(y, 3, 14)))
        report_id = db.execute(
            text(
                "SELECT id FROM reporting.saved_reports WHERE builtin_key = 'annual_programme' "
                "AND tenant_id = :t AND deleted_at IS NULL"
            ),
            {"t": activity.tenant_id},
        ).scalar_one()
        db.commit()
        return report_id, year, mark
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser_and_report():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    report_id, year, mark = _situation()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), report_id, year, mark
        b.close()


def _open(browser_and_report, width: int):
    b, session, report_id, year, mark = browser_and_report
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session)
    page.goto(f"/admin/rapporten/{report_id}")
    pagina_klaar(page)
    return page, year, mark


def _shot(page, name: str) -> None:
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.locator("#rp-filters").scroll_into_view_if_needed()
        page.screenshot(path=f"{SHOTS}/{name}.png", full_page=True)


@pytest.mark.parametrize("width", [390, 1280])
def test_the_filter_block_stays_within_the_width(browser_and_report, width):
    page, _year, _mark = _open(browser_and_report, width)
    m = page.evaluate(_MEASURE)
    print("MEASURE", width, m)
    _shot(page, f"{width}-filter")
    page.close()

    assert m["block"] and m["box"], m
    assert m["block"]["right"] <= width and m["box"]["right"] <= m["block"]["right"], m
    assert m["rows"], "the filter offers ticks"
    assert all(row["h"] >= 44 for row in m["rows"]), m["rows"]
    assert [row["text"] for row in m["rows"] if row["checked"]] == ["Dit jaar"], m["rows"]


def test_a_click_on_next_year_keeps_both_ticks(browser_and_report):
    page, year, mark = _open(browser_and_report, 390)
    page.locator("#rp-filters label", has_text=str(year + 1)).click()
    page.wait_for_function(
        f"""() => [...document.querySelectorAll('#rp-filters label')]
                .some(l => l.textContent.trim() === '{year + 1}' && l.querySelector('input').checked)"""
    )
    pagina_klaar(page)
    m = page.evaluate(_MEASURE)
    names = page.evaluate(
        f"() => [...document.querySelectorAll('td')].map(t => t.textContent.trim())"
        f".filter(t => t.endsWith('{mark}'))"
    )
    print("MEASURE click", [r for r in m["rows"] if r["checked"]], names)
    _shot(page, "390-two-ticks")
    page.close()

    assert {r["text"] for r in m["rows"] if r["checked"]} == {"Dit jaar", str(year + 1)}, m
    assert sorted(set(names)) == [f"Vinkje {year} {mark}", f"Vinkje {year + 1} {mark}"], names


_VISIBLE = """(years) => {
  const box = document.querySelector('#rp-filters fieldset > div');
  const b = box.getBoundingClientRect();
  return {scrollTop: box.scrollTop, box: [Math.round(b.top), Math.round(b.bottom)],
          rows: [...box.querySelectorAll('label')].map(l => {
            const r = l.getBoundingClientRect();
            return {text: l.textContent.trim(), top: Math.round(r.top), bottom: Math.round(r.bottom)};
          }).filter(r => years.includes(r.text) || r.text === 'Dit jaar')};
}"""


def test_this_year_and_next_show_without_scrolling(browser_and_report):
    """#1453, measured at 390 px on the shipped annual programme."""
    page, year, _mark = _open(browser_and_report, 390)
    m = page.evaluate(_VISIBLE, [str(year), str(year + 1)])
    print("MEASURE visible", m)
    page.close()

    assert m["scrollTop"] == 0, m
    texts = [r["text"] for r in m["rows"]]
    assert texts == ["Dit jaar", str(year + 1), str(year)], f"order under Dit jaar: {texts}"
    top, bottom = m["box"]
    for row in m["rows"]:
        assert top <= row["top"] and row["bottom"] <= bottom, f"{row} outside the box {m['box']}"
