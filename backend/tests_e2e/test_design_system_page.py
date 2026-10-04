"""E2E: the kit page itself (`/admin/design-system`) — CR-11 pilot A, K9 (#1563).

The page renders every macro live, so it is the first screen to show a macro
that breaks. Two things nothing measured:

- **No script error while the page starts.** On 4 October 2026 the page threw
  "edit is not defined" twice: the demo of the detail screen rendered
  `ui.edit_toggle("edit")` without an `x-data` that declares `edit`. Nothing was
  red, because no test listened.
- **No overflow at 390 px**, the acceptance of K9: every block of pilot A stands
  on the page, and a block that widens the page there widens a phone.

Broken on purpose (5 October 2026): the `x-data` taken off the detail demo again
→ the error tests red with "edit is not defined"; the one off the section bar →
"sedit is not defined"; a `<div style="width: 30rem">` added above section 2 →
the width test red at 390 px with 496 against 390; `px-3` back on the status
filter's segments → 398 (the demo of three segments reaches past its card);
`flex-wrap` off the section header → 392 (the action button of section 6).

The width test found those last two on its first run: both were kit macros, and
both are repaired there (#1563).
"""

import os
import re
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin, pagina_klaar  # noqa: E402

PAGE = "/admin/design-system"

#: The page's width, and the innermost elements that reach past the window —
#: so a red run says where to look.
_WIDTH = """() => {
  const w = window.innerWidth;
  const past = [...document.querySelectorAll('main *')].filter(e => {
    const b = e.getBoundingClientRect();
    return b.width > 0 && b.right > w + 0.5 && ![...e.children].some(c => c.getBoundingClientRect().right > w + 0.5);
  });
  const visible = past.filter(e => { for (let p = e.parentElement; p; p = p.parentElement) {
      const o = getComputedStyle(p).overflowX; if (o !== 'visible') return false; } return true; });
  return {page: document.documentElement.scrollWidth, window: w,
          out: visible.slice(0, 5).map(e => `${e.tagName.toLowerCase()}.${(e.className || '').toString().slice(0, 60)} → ${Math.round(e.getBoundingClientRect().right)}`)};
}"""
WIDTHS = (390, 1440, 1920)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _open(browser, width: int):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on(
        "console",
        lambda m: page.errors.append(m.text) if m.type == "error" else None,
    )
    login_als_admin(page, email, make_session_value(email))
    page.goto(PAGE)
    pagina_klaar(page)
    return page


@pytest.mark.parametrize("width", WIDTHS)
def test_the_kit_page_starts_without_a_script_error(browser, width):
    page = _open(browser, width)
    try:
        sections = page.locator("h3", has_text=re.compile(r"^\d+\w* · ")).count()
        assert sections >= 25, f"only {sections} sections rendered — is this the kit page?"
        assert page.errors == []
    finally:
        page.close()


@pytest.mark.parametrize("width", WIDTHS)
def test_the_kit_page_is_as_wide_as_the_window(browser, width):
    page = _open(browser, width)
    try:
        measured = page.evaluate(_WIDTH)
        assert measured["window"] == width
        assert measured["page"] == width, (
            f"the page is {measured['page']} px wide in a window of {width}; sticking out: "
            f"{measured['out']}"
        )
    finally:
        page.close()


def test_the_edit_toggle_of_the_detail_demo_works(browser):
    """The button that threw: it is there, and a click hides it (its own state
    says "editing" now)."""
    page = _open(browser, 1440)
    try:
        card = page.locator("h3", has_text="Voorbeeldactiviteit").locator("xpath=..")
        button = card.get_by_role("button", name="Bewerken")
        assert button.is_visible()
        button.click()
        button.wait_for(state="hidden", timeout=2000)
        assert page.errors == []
    finally:
        page.close()
