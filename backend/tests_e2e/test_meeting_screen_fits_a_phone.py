"""#1236 — the meeting screen fits a 390 px phone and does not scroll sideways.

Measured on 27 September 2026, before the fix: at 390 px the meeting document was
455 px wide. Two elements stuck out:

  - the "Uploaden" button, right edge 455 px. Its form is a flex row whose upload
    field sits in a `flex-1` box; a flex item does not shrink below its content
    width unless it carries `min-w-0`, so the button was pushed off screen;
  - "komt vóór Varia", right edge 396 px. The add-section form is a flex row
    without `flex-wrap`, holding a `w-64` input, a button and that hint.

Why an e2e test and not a render test: the markup was valid. Only a browser
knows how wide the upload field's content is and whether a row fits.

Red proof (run, both directions): with `min-w-0` removed from the upload row and
`flex-wrap` removed from the section row, and the css rebuilt, the phone test
fails with the page width and both offenders by name; with them back it passes.
The desktop test guards the other half of the issue: at 1440 px both rows stay
on one line, which is what they did before the fix.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin  # noqa: E402

PHONE = 390

# Every element whose right edge passes the viewport, named by tag and text, so a
# failure says what sticks out instead of only that something does.
_OFFENDERS = """(limit) => [...document.querySelectorAll('#vg-document *')]
  .map(el => ({el, r: el.getBoundingClientRect()}))
  .filter(({r}) => r.width > 0 && Math.round(r.right) > limit)
  .map(({el, r}) => `${el.tagName.toLowerCase()} "${(el.innerText || el.value || '')
    .trim().slice(0, 30)}" right=${Math.round(r.right)}`)"""

# The two rows the issue names, located by what they post to, not by position.
_ROWS = {
    "section": "#vg-document form[hx-post$='/sectie']",
    "upload": "#vg-document form[hx-post$='/bijlage']",
}


def _missing(reason: str) -> None:
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e seed loaded but: {reason}")
    pytest.skip(reason)


@pytest.fixture(scope="module")
def browser():
    try:
        from app.domains.auth.api import make_session_value
        from tests.conftest import SEEDED_ADMIN_EMAIL

        email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
        session_value = make_session_value(email)
    except Exception as exc:  # pragma: no cover - only in a bare environment
        pytest.skip(f"backend not importable for the session value: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, email, session_value
        b.close()


def _open_new_meeting(browser, width: int, date: str):
    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_als_admin(page, email, session_value)
    page.goto("/admin/vergaderingen/nieuw")
    if page.locator("#vg-datum").count() == 0:
        page.close()
        _missing("admin session not accepted, or the meeting screen is absent")
    page.fill("#vg-datum", date)
    page.click("button[type=submit]")
    page.wait_for_selector("#vg-document", timeout=10_000)
    return page


def _assert_rows_rendered(page) -> None:
    """Both rows must be on the page and visible — else a narrow page proves nothing."""
    for name, selector in _ROWS.items():
        row = page.locator(selector)
        assert row.count() == 1, f"the {name} row is not on the page ({selector})"
        assert row.is_visible(), f"the {name} row is not visible"


def test_the_meeting_screen_does_not_scroll_sideways_on_a_phone(browser):
    page = _open_new_meeting(browser, PHONE, "2026-12-03")
    try:
        _assert_rows_rendered(page)
        width = page.evaluate("document.documentElement.scrollWidth")
        offenders = page.evaluate(_OFFENDERS, PHONE)
        assert width <= PHONE and not offenders, (
            f"the meeting screen is {width} px wide at {PHONE} px; sticking out: {offenders}")
        # The degenerate case: a row squeezed to nothing also fits. The upload button
        # must still sit fully inside the viewport and have its own width.
        button = page.locator(_ROWS["upload"] + " button[type=submit]").bounding_box()
        assert button and button["width"] > 40 and button["x"] + button["width"] <= PHONE, (
            f"the upload button is not usable at {PHONE} px: {button}")
    finally:
        page.close()


def test_both_rows_stay_on_one_line_on_a_desktop(browser):
    page = _open_new_meeting(browser, 1440, "2026-12-10")
    try:
        _assert_rows_rendered(page)
        for name, selector in _ROWS.items():
            boxes = page.evaluate(
                """(sel) => [...document.querySelector(sel).children]
                    .filter(c => c.type !== 'hidden')
                    .map(c => { const r = c.getBoundingClientRect();
                                return [Math.round(r.top), Math.round(r.bottom)]; })""",
                selector)
            assert len(boxes) >= 2, f"the {name} row has fewer than two visible children: {boxes}"
            # One line means every child overlaps the first one vertically. The rows
            # align their children differently (centre, bottom), so equal tops would be
            # the wrong test; a wrapped child starts below the first child's bottom.
            first_top, first_bottom = boxes[0]
            wrapped = [b for b in boxes[1:] if b[0] >= first_bottom or b[1] <= first_top]
            assert not wrapped, (
                f"the {name} row wraps on a 1440 px desktop: child boxes {boxes}")
    finally:
        page.close()
