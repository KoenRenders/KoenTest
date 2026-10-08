"""E2E: the record head on the activity (CR-11 block 5, #1557).

Measured from the rendered DOM (design-system-end-state §2.2, §3.9, §3.12):

- 390 px: the page is as wide as the phone (it was 912), on every tab;
- the title goes first: a long title takes the whole row — never a narrow
  column beside the controls — and the controls sit under it, at the right,
  inside the gutter;
- the frame does not move between tabs: way back, title, controls, facts and tab
  line keep their place and size;
- the way back returns to the list as it was left, also after a tab change;
- the facts line reads the same words at 390 and at 1 440 px;
- the Acties menu stays inside the screen, and Escape gives the focus back.

Screenshots go outside the repo.
"""

import os
import sys
from datetime import date, time, timedelta

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHORT = "Kophoofd kort"
LONG = "Kophoofd met een uitzonderlijk lange titel voor barbecue, kinderanimatie en avondconcert"
GUTTER = 16

_PARTS = [
    "[data-way-back]",
    "[data-title-group]",
    "[data-head-controls]",
    "[data-facts]",
    "[data-related-tabs]",
]

_FRAME = """(parts) => {
  const r = e => { const b = e.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top + scrollY), Math.round(b.width), Math.round(b.height)]; };
  const out = {page: [document.documentElement.scrollWidth, innerWidth]};
  for (const s of parts) out[s] = r(document.querySelector(s));
  out.h1 = r(document.querySelector('[data-record-head] h1'));
  out.facts_text = document.querySelector('[data-facts]').innerText.replace(/\\s+/g, ' ').trim();
  return out;
}"""


def _activity(name: str) -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate

    db = SessionLocal()
    try:
        existing = db.query(Activity).filter(Activity.name == name).first()
        if existing is not None:
            return existing.id
        activity = Activity(name=name, location="Parochiezaal")
        db.add(activity)
        db.flush()
        db.add(
            ActivityDate(
                activity_id=activity.id,
                start_date=date.today() + timedelta(days=90),
                start_time=time(14, 0),
                end_time=time(17, 30),
            )
        )
        db.commit()
        return activity.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    ids = {"short": _activity(SHORT), "long": _activity(LONG)}
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), ids
        b.close()


def _page(setup, width: int, path: str):
    b, session, _ids = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    login_met_sessie(page, session)
    page.goto(path)
    pagina_klaar(page)
    return page


def _frame(page) -> dict:
    return page.evaluate(_FRAME, _PARTS)


def test_the_activity_is_as_wide_as_the_phone_on_every_tab(setup):
    ids = setup[2]
    for key in ("short", "long"):
        for tab in ("", "/inschrijvingen", "/betalingen"):
            page = _page(setup, 390, f"/admin/activiteiten/{ids[key]}{tab}")
            assert _frame(page)["page"] == [390, 390], (key, tab)
            page.close()


def test_a_long_title_takes_the_row_and_the_controls_go_under_it(setup):
    page = _page(setup, 390, f"/admin/activiteiten/{setup[2]['long']}")
    f = _frame(page)
    row = 390 - 2 * GUTTER
    gx, gy, gw, gh = f["[data-title-group]"]
    cx, cy, cw, ch = f["[data-head-controls]"]
    assert (gx, gw) == (GUTTER, row), "the title group takes the whole row"
    assert f["h1"][2] == row, "never a title in a narrow column"
    assert f["h1"][3] > 36, "the long title wraps instead of being cut"
    assert cy >= gy + gh, "the controls sit under the title"
    assert cx + cw == 390 - GUTTER, "at the right, inside the gutter"
    page.close()


def test_the_title_comes_before_the_controls_on_a_phone(setup):
    """Also a short title: the title is never below or right of the controls'
    start, and the controls never leave the gutter."""
    page = _page(setup, 390, f"/admin/activiteiten/{setup[2]['short']}")
    f = _frame(page)
    assert f["h1"][0] == GUTTER
    assert f["h1"][1] <= f["[data-head-controls]"][1]
    cx, _cy, cw, _ch = f["[data-head-controls]"]
    assert cx >= GUTTER and cx + cw <= 390 - GUTTER
    page.close()


def test_the_title_never_shares_a_narrow_column_with_narrow_controls(setup):
    """The case the rule is for: two narrow controls that WOULD fit beside a
    squeezed title. The kit demo has exactly that (no assistant overlay beside
    them). The title group may not shrink on a phone, so it takes the row and
    the controls go under it.

    Proven red by letting the group shrink (`flex-[1_1_0%]` below md): the title
    then stands in a column of 79 px (row 308) beside the controls. The activity itself
    cannot show this while the assistant overlay (#1562) fills the controls' row.
    """
    page = _page(setup, 390, "/admin/design-system")
    m = page.evaluate(
        """() => {
      const head = document.querySelector('[data-kit-record-head] [data-record-head]');
      const r = s => { const b = head.querySelector(s).getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)]; };
      return {row: Math.round(head.getBoundingClientRect().width), group: r('[data-title-group]'), controls: r('[data-head-controls]')};
    }"""
    )
    assert m["controls"][2] < m["row"] / 2 + 60, (
        "the controls are narrow here, or the test proves nothing"
    )
    assert m["group"][2] == m["row"], "the title group takes the whole row"
    assert m["controls"][1] >= m["group"][1] + m["group"][3], "the controls sit under it"
    page.close()


@pytest.mark.parametrize("width", [390, 1440])
def test_the_frame_does_not_move_between_tabs(setup, width):
    base = f"/admin/activiteiten/{setup[2]['short']}"
    frames = []
    for tab in ("", "/inschrijvingen", "/betalingen"):
        page = _page(setup, width, base + tab)
        f = _frame(page)
        frames.append({part: f[part] for part in _PARTS})
        page.close()
    assert frames[0] == frames[1] == frames[2]


def test_the_facts_read_the_same_words_at_every_width(setup):
    path = f"/admin/activiteiten/{setup[2]['short']}"
    texts = []
    for width in (390, 1440):
        page = _page(setup, width, path)
        texts.append(_frame(page)["facts_text"])
        page.close()
    assert texts[0] == texts[1]
    assert (
        "14:00–17:30" in texts[0] and "Parochiezaal" in texts[0] and "Publieke pagina" in texts[0]
    )


def test_the_way_back_returns_to_the_list_as_it_was_left(setup):
    """From the list with a scope and a search term, through a tab change, back:
    the same address, and the search field still holds the term."""
    page = _page(setup, 390, "/admin/activiteiten?scope=all&q=Kophoofd+kort")
    page.click(f'a[href^="/admin/activiteiten/{setup[2]["short"]}?terug="]')
    pagina_klaar(page)
    assert page.locator("[data-way-back]").inner_text().strip() == "Activiteiten"
    page.click('[data-related-tabs] a:has-text("Inschrijvingen")')
    pagina_klaar(page)
    assert (
        page.locator("[data-related-tabs] a[aria-current=page]")
        .inner_text()
        .startswith("Inschrijvingen")
    )
    page.click("[data-way-back]")
    pagina_klaar(page)
    assert page.url.endswith("/admin/activiteiten?scope=all&q=Kophoofd+kort")
    assert page.locator('input[name="q"]').first.input_value() == "Kophoofd kort"
    assert page.locator(f"text={SHORT}").count() >= 1
    page.close()


@pytest.mark.parametrize("width", [390, 1440])
def test_the_actions_menu_stays_on_screen_and_escape_returns_the_focus(setup, width):
    page = _page(setup, width, f"/admin/activiteiten/{setup[2]['short']}")
    assert page.locator("[data-actions-menu]").is_hidden()
    page.click("[data-actions-trigger]")
    page.wait_for_selector("[data-actions-menu]", state="visible")
    box = page.locator("[data-actions-menu]").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    assert round(box["width"]) == 272
    heights = page.evaluate(
        "() => [...document.querySelectorAll('[data-actions-menu] [role=menuitem]')].map(e => e.getBoundingClientRect().height)"
    )
    assert heights and min(heights) >= 44, "every item is a touch target"
    assert page.get_attribute("[data-actions-trigger]", "aria-expanded") == "true"
    page.keyboard.press("Escape")
    page.wait_for_selector("[data-actions-menu]", state="hidden")
    assert page.evaluate("document.activeElement.hasAttribute('data-actions-trigger')")
    page.close()


def test_bewerken_opens_the_edit_state_of_the_same_page(setup):
    base = f"/admin/activiteiten/{setup[2]['short']}"
    page = _page(setup, 1440, base)
    page.click('[data-head-controls] a:has-text("Bewerken")')
    pagina_klaar(page)
    assert page.url.endswith(f"{base}?bewerken=1")
    badges = page.locator("[data-badges] > *").all_inner_texts()
    assert "Bewerken" in [b.strip() for b in badges[1:]], "after the status"
    assert page.locator('[data-head-controls] a:has-text("Bewerken")').count() == 0
    assert page.locator("[data-actions-trigger]").count() == 1
    page.close()
