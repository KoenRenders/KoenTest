"""E2E: read mode keeps the edit grid, its rows 4 px apart (#1928; end state §2.2).

Koen, 12 October 2026: "gelieve de lijnafstand tussen de velden gelijk te
zetten aan gezin en aan de personen daar … consistent over al de schermen
heen". Read on the seeded activity, a booking and a household:

- **the same distance on every record**: between two rows of facts 4 px — on
  the activity's card, on a component's card, on the booking and on the
  household's person card, which is the measure;
- **half beside half on a desktop**: Doelpubliek and Enkel leden, Status and
  the paid amount, stand on one row, the second where the grid's third track
  starts;
- **one column on a phone**: every fact a row of its own, the same 4 px apart.

Broken on purpose (13 October 2026, each put back and the css rebuilt):
- the read rule out of `scripts/build-css.sh` (the grid's own 12 px) → the
  distance test red;
- the rule set to 8 px → the distance test red;
- the booking's amount on a full cell → "Status and the amount are not on one
  row at 1 440 px".
"""

import os
import sys
from urllib.parse import urljoin

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin, pagina_klaar  # noqa: E402

#: The distance the kit sets between two rows of facts, and the person card's.
ROW_GAP = 4

BLOCKS = {
    "the activity": "[data-activity-facts]",
    "a component": "[data-component-facts]",
    "the booking": "[data-booking-facts]",
    "the person card": "[data-person-card] [data-person-name]",
}

#: The facts of a block as [left, top, bottom], in document order. The person
#: card's lines are the paragraphs under its name.
MEASURE = """(sel) => {
  let root = document.querySelector(sel);
  if (!root) return null;
  if (root.matches('[data-person-name]')) root = root.closest('[data-person-card]');
  return [...root.querySelectorAll('p')].filter(p => p.checkVisibility()).map(p => {
    const b = p.getBoundingClientRect();
    return [Math.round(b.left * 10) / 10, Math.round(b.top * 10) / 10, Math.round(b.bottom * 10) / 10];
  });
}"""


@pytest.fixture(scope="module")
def measured():
    """{(block, width): its facts}, each read after a full load."""
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    found = {}
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
        login_als_admin(page, email, make_session_value(email))

        def first(path, selector):
            page.goto(path)
            pagina_klaar(page)
            return urljoin(page.url, page.locator(selector).first.get_attribute("href"))

        page.goto("/admin/activiteiten")
        pagina_klaar(page)
        activity = urljoin(
            page.url, page.get_by_role("link", name="E2E-activiteit").first.get_attribute("href")
        )
        pages = {
            "the activity": activity,
            "a component": activity,
            "the booking": first("/admin/betalingen", "a[data-row-link]"),
            "the person card": first("/admin/leden", "#leden-lijst a[data-row-link]"),
        }
        for width in (390, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            for block, path in pages.items():
                page.goto(path)
                pagina_klaar(page)
                found[block, width] = page.evaluate(MEASURE, BLOCKS[block])
        browser.close()
    return found


def _rows(facts):
    """The facts grouped into rows: [(top, bottom, [lefts])], top to bottom."""
    rows = []
    for left, top, bottom in facts:
        if rows and abs(rows[-1][0] - top) < 1:
            rows[-1] = (rows[-1][0], max(rows[-1][1], bottom), rows[-1][2] + [left])
        else:
            rows.append((top, bottom, [left]))
    return rows


def test_the_rows_of_facts_are_four_pixels_apart_on_every_record(measured):
    for (block, width), facts in measured.items():
        assert facts, f"{block} at {width} px: no facts found — looked nowhere"
        rows = _rows(facts)
        assert len(rows) >= 2, f"{block} at {width} px: one row of facts, no distance to read"
        for upper, lower in zip(rows, rows[1:]):
            gap = lower[0] - upper[1]
            assert abs(gap - ROW_GAP) <= 0.5, (
                f"{block} at {width} px: rows {gap} px apart, the kit sets {ROW_GAP}"
            )


def test_half_stands_beside_half_on_a_desktop_and_under_it_on_a_phone(measured):
    for block, what in (
        ("the activity", "Doelpubliek and Enkel leden"),
        ("the booking", "Status and the amount"),
    ):
        wide = _rows(measured[block, 1440])
        pairs = [row for row in wide if len(row[2]) == 2]
        assert pairs, f"{what} are not on one row at 1 440 px: {wide}"
        for _top, _bottom, lefts in pairs:
            assert lefts[1] - lefts[0] > 300, f"{what}: the second fact is not in the right half"
        narrow = _rows(measured[block, 390])
        assert all(len(row[2]) == 1 for row in narrow), f"{block} at 390 px is not one column"
        assert len(narrow) == len(measured[block, 390])
