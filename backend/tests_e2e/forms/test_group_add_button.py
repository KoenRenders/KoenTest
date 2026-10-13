"""E2E: the add action of a repeating group does not look like a field (#1972).

"+ E-mailadres" on Word lid read as a text field at first sight (Koen,
13 October 2026): a white box with a grey line at an input's height, among
fields. Measured in the rendered DOM, at 390 and 1 440 px, on Word lid, a
household in edit mode and the activity in edit mode (the heaviest screen):

- the action's background is not an input's and not its card's, and it has no
  line: the tint is what sets it apart;
- its box is where it was: the same button with the look it had (white, a grey
  line) has the same box, to the pixel;
- it is a button of the kit's touch height on a phone, and nothing scrolls
  sideways.

Broken on purpose (13 October 2026, each put back):
- the `quiet` variant given `bg-white` → "the add action has an input's
  background";
- the `quiet` variant given `border-gray-300` → "the add action has a line";
- `border border-transparent` taken out of the variant → "the look it had was
  not put on: nothing compared" — the comparison refuses to pass blind.

The box comparison is a measurement, not a guard one can break in the kit: it
puts the look the button had (`OLD`) in the place of today's (`NEW`), both as
this file writes them, and finds the same box. A variant that no longer is
`NEW` is what the proof above meets.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

NEW = "bg-blue-50 hover:bg-blue-100 border border-transparent text-blue-700"
OLD = "bg-white border border-gray-300 hover:bg-gray-100 text-gray-800"

_MEASURE = """([fresh, former]) => {
  const box = e => { const b = e.getBoundingClientRect(); return [b.left, b.top + scrollY, b.width, b.height].map(v => Math.round(v * 10) / 10); };
  const paint = e => getComputedStyle(e).backgroundColor;
  const solid = c => !/rgba\\(.*,\\s*0\\)$/.test(c) && c !== 'transparent';
  const behind = e => { let p = e.parentElement; while (p && !solid(paint(p))) p = p.parentElement; return p ? paint(p) : null; };
  const input = [...document.querySelectorAll('input[type=text], input[type=email], input:not([type])')].find(i => i.checkVisibility());
  return {
    page: [document.documentElement.scrollWidth, innerWidth],
    input: input ? {background: paint(input), line: getComputedStyle(input).borderTopColor} : null,
    actions: [...document.querySelectorAll('[data-group-add]')].filter(b => b.checkVisibility()).map(b => {
      const now = box(b), style = getComputedStyle(b);
      const seen = {label: b.textContent.trim(), tag: b.tagName, type: b.type, background: style.backgroundColor,
                    line: style.borderTopColor, line_width: parseFloat(style.borderTopWidth), colour: style.color, behind: behind(b), box: now};
      const classes = b.className;
      b.className = classes.replace(fresh, former);
      seen.swapped = b.className !== classes;
      seen.box_before = box(b);
      b.className = classes;
      return seen;
    }),
  };
}"""


@pytest.fixture(scope="module")
def browser():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _first_record(page, list_path: str) -> str:
    """The edit state of the first record of a back-office list."""
    page.goto(list_path)
    pagina_klaar(page)
    href = page.locator("a[data-row-link]").first.get_attribute("href")
    assert href, f"no record on {list_path} in the seeded data"
    return href.split("?")[0] + "?bewerken=1"


SCREENS = {
    "word-lid": lambda page: "/lid-worden",
    "gezin-bewerken": lambda page: _first_record(page, "/admin/leden"),
    "activiteit-bewerken": lambda page: _first_record(page, "/admin/activiteiten"),
}


@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_the_add_action_is_no_field_and_stands_where_it_stood(browser, screen, width):
    b, session = browser
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session)
    page.goto(SCREENS[screen](page))
    pagina_klaar(page)
    seen = page.evaluate(_MEASURE, [NEW, OLD])
    print("MEASURE add action", screen, width, seen["page"], seen["input"], seen["actions"])

    assert seen["actions"], f"no add action on {screen}: nothing measured"
    assert seen["input"], f"no input on {screen} to tell the action from"
    assert seen["page"][0] <= seen["page"][1], f"a sideways scroll: {seen['page']}"
    for action in seen["actions"]:
        where = f"{screen} @{width} “{action['label']}”"
        assert action["tag"] == "BUTTON" and action["type"] == "button", where
        assert action["background"] != seen["input"]["background"], (
            f"the add action has an input's background: {where}"
        )
        assert action["background"] != action["behind"], (
            f"the add action has its card's colour: {where}"
        )
        seen_line = action["line_width"] > 0 and not action["line"].replace(" ", "").endswith(",0)")
        assert not seen_line, f"the add action has a line: {where}"
        assert action["swapped"], "the look it had was not put on: nothing compared"
        assert action["box"] == action["box_before"], f"the box moved: {where}"
        if width < 768:
            assert action["box"][3] >= 44, f"under the touch height: {where}"
    page.close()


def test_the_kit_page_shows_it_beside_what_it_is_not(browser):
    """A primary, a secondary, the add action, a badge and an input in one row:
    five backgrounds or lines, and the add action shares none of them."""
    b, session = browser
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    login_met_sessie(page, session)
    page.goto("/admin/design-system")
    pagina_klaar(page)
    row = page.evaluate(
        """() => { const r = document.querySelector('[data-kit-add-action]');
          const look = e => [getComputedStyle(e).backgroundColor, getComputedStyle(e).borderTopColor];
          const buttons = [...r.querySelectorAll('button')];
          return {primary: look(buttons[0]), secondary: look(buttons[1]), add: look(r.querySelector('[data-group-add]')),
                  badge: look(r.querySelector('[data-badge]')), input: look(r.querySelector('input'))}; }"""
    )
    print("MEASURE kit row", row)
    others = {name: look for name, look in row.items() if name != "add"}
    assert len(others) == 4
    for name, look in others.items():
        assert look[0] != row["add"][0], f"the add action has the background of the {name}"
    page.close()
