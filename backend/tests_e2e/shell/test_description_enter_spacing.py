"""E2E: a little space at every Enter in an activity's description (#1688).

Measured in a browser, because it is the page's own rule that gives the space:
the distance between the last line of one statement and the first line of the
next, after ONE Enter and after a blank line, at 390 and at 1440 px.

Before: a single Enter was a `<br>` — the next statement stood at the ordinary
line distance (0 px between the two line boxes), so a statement that wrapped
could not be told from the next one. Now 8 px, and a blank line keeps 16 px.

Broken on purpose (7 October 2026): the page's rule for a line taken off the
description → 0 px after an Enter; the two gaps made equal → the test that
tells them apart.
"""

import os
import sys
from datetime import date, timedelta

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

DESCRIPTION = (
    "Iedereen is welkom, jong en oud.\n"
    "We vertrekken om tien uur aan het Dorpsplein en wandelen dan samen langs de vaart tot aan de"
    " oude molen, waar een drankje klaarstaat voor elke deelnemer.\n"
    "Honden mogen mee aan de leiband.\n"
    "Breng stevige schoenen en bij regen een jas mee, want we wandelen ook bij minder goed weer"
    " en schuilen kan onderweg nergens.\n"
    "Inschrijven is niet nodig.\n"
    "\n"
    "Na de wandeling is er soep in de zaal."
)

#: Per source line of the description: the top of its first line box and the
#: bottom of its last, and how many line boxes it takes.
_LINES = """() => { const root = document.querySelector('[data-activity-description]');
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const out = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (!n.textContent.trim()) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const rects = [...range.getClientRects()];
    out.push({text: n.textContent.trim().slice(0, 18), top: rects[0].top, bottom: rects[rects.length - 1].bottom,
              boxes: new Set(rects.map(r => Math.round(r.top))).size});
  }
  const style = getComputedStyle(root);
  return {lines: out, font: style.fontSize, line: style.lineHeight, width: root.getBoundingClientRect().width,
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.fixture(scope="module")
def activity():
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities import service
    from app.domains.activities.api import Activity, ActivityDate

    db = SessionLocal()
    row = Activity(name="Wandeling met regels 1688", location="Dorpsplein", description=DESCRIPTION)
    db.add(row)
    db.flush()
    db.add(ActivityDate(activity_id=row.id, start_date=date.today() + timedelta(days=30)))
    db.commit()
    activity_id = row.id
    db.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield browser, activity_id
        browser.close()
    db = SessionLocal()
    try:
        service.delete_activity(db, activity_id, actor="e2e-1688@example.com")
    finally:
        db.close()


@pytest.mark.parametrize("width", [390, 1440])
def test_one_enter_gives_a_small_space_and_a_blank_line_a_larger_one(activity, width):
    """Red on master: 0 px after one Enter."""
    browser, activity_id = activity
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        page.goto(f"/activiteiten/{activity_id}")
        pagina_klaar(page)
        m = page.evaluate(_LINES)
        lines = m["lines"]
        gaps = [round(lines[i + 1]["top"] - lines[i]["bottom"], 1) for i in range(len(lines) - 1)]
        print(
            "MEASURE description",
            width,
            {
                "gaps": gaps,
                "boxes": [ln["boxes"] for ln in lines],
                "font": m["font"],
                "line": m["line"],
            },
        )
        assert len(lines) == 6, [ln["text"] for ln in lines]
        assert (m["font"], m["line"]) == ("16px", "24px"), "the reading text changed (#1647)"
        if width == 390:
            assert sum(ln["boxes"] > 1 for ln in lines) >= 2, (
                "no statement wraps: nothing to tell apart"
            )
        # Four single Enters, then the blank line. Text sits in a 24 px line box
        # with its glyph box a little lower than the line: the gap between two
        # ranges is the space above the line, give or take the font's own leading.
        enters, blank = gaps[:4], gaps[4]
        plain = 24 - (lines[0]["bottom"] - lines[0]["top"]) / lines[0]["boxes"]
        assert all(abs((gap - plain) - 8) <= 1 for gap in enters), (enters, plain)
        assert abs((blank - plain) - 16) <= 1, (blank, plain)
        assert blank - max(enters) >= 6, "a blank line and one Enter cannot be told apart"
        assert m["page"] == [width, width]
    finally:
        page.close()
