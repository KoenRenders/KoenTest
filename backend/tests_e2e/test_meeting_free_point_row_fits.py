"""E2E: with "Punt toevoegen" open, the free-point row fits the meeting screen (#1339).

Found while building #1335: at 390 px the "Toevoegen" button beside "Typ een vrij
punt" ended at 422 px and the page scrolled sideways. The input is a `flex-1` item,
and a flex item does not shrink below its content width without `min-w-0` — an
`<input>` has an intrinsic width of about twenty characters. The same cause as the
upload row in #1236, one screen further.

Proven red against master `08beaa85` (29 September 2026): "@390: the page is 422 px
wide; Toevoegen ends at 422, its picker box at 353".
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_als_admin  # noqa: E402

SHOTS = "/scratch/shots_1339"

# The free-point form inside the open picker, its button and the picker box.
_MEASURE = """() => {
  const form = document.querySelector('#vg-document form input[name=title]').closest('form');
  const box = form.closest('div.rounded-lg').getBoundingClientRect();
  const input = form.querySelector('input[name=title]').getBoundingClientRect();
  const button = form.querySelector('button[type=submit]').getBoundingClientRect();
  return {
    doc: document.documentElement.scrollWidth, vw: innerWidth,
    box_right: Math.round(box.right),
    input_width: Math.round(input.width),
    button_left: Math.round(button.left), button_right: Math.round(button.right),
    button_width: Math.round(button.width),
    button_top: Math.round(button.top), input_top: Math.round(input.top),
  };
}"""


@pytest.fixture(scope="module")
def browser():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, email, make_session_value(email)
        b.close()


@pytest.mark.parametrize(("width", "day"), [(390, "2027-10-07"), (1280, "2027-10-14")])
def test_the_free_point_row_fits_with_the_picker_open(browser, width, day):
    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto("/admin/vergaderingen/nieuw")
        page.fill("#vg-datum", day)
        page.click("button[type=submit]")
        page.wait_for_selector("#vg-document", timeout=10_000)
        page.locator("#vg-document button", has_text="Punt toevoegen").first.click()
        htmx_stil(page)

        m = page.evaluate(_MEASURE)
        print(f"MEASURE @{width}", m)
        assert m["doc"] <= m["vw"] and m["button_right"] <= m["box_right"], (
            f"@{width}: the page is {m['doc']} px wide; Toevoegen ends at "
            f"{m['button_right']}, its picker box at {m['box_right']}"
        )
        # The degenerate case: a field squeezed to nothing also fits. It must keep a
        # width to type in, and the button its own width, on the same line.
        assert m["input_width"] >= 120 and m["button_width"] > 60, m
        assert abs(m["button_top"] - m["input_top"]) < 12, f"the row wrapped: {m}"

        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.get_by_placeholder("Typ een vrij punt").scroll_into_view_if_needed()
            page.wait_for_function(
                "() => document.getAnimations().every(a => a.playState !== 'running')"
            )
            page.screenshot(path=f"{SHOTS}/{width}-vrij-punt.png")
    finally:
        page.close()
