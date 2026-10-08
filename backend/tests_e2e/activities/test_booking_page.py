"""E2E: the booking page in a browser (#1574, CR-11 pilot A).

What a server test cannot see: that the page fits at three widths, that the
title comes first on a phone, and that a save through htmx swaps the whole page
and leaves one shell, one record head and a confirmation.

- At 1 920, 1 440 and 390 px: no horizontal overflow; the way back, the title,
  the status badge and the facts line are in view; on a phone the head's
  controls do not push the title away (the title is at the left edge, above or
  beside them).
- Saving the note on the page: the answer is the page again — one shell, one
  record head, the note in the figures, a toast — and the way back still leads
  to the list as it was left.

The booking is the first open one of the seeded list. Only its note changes,
and the test puts the old note back.

Proven red (on this branch, restored after): `X-Booking-Page` taken off the
edit form → the save test fails (the list fragment lands in the body: no record
head left).
"""

import os
import re
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar, toasts  # noqa: E402

LIST = "/admin/betalingen?zicht=openstaand"

_GEOMETRY = """() => {
  const box = s => { const e = document.querySelector(s); if (!e || !e.checkVisibility()) return null;
    const r = e.getBoundingClientRect(); return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)}; };
  return {
    back: box('[data-way-back]'), title: box('[data-record-head] h1'), badges: box('[data-badges]'),
    controls: box('[data-head-controls]'), figures: box('[data-booking-figures]'),
    edit: box('[data-booking-edit]'),
    heads: document.querySelectorAll('[data-record-head]').length,
    shells: document.querySelectorAll('#admin-zijbalk').length,
    scroll: document.documentElement.scrollWidth, width: innerWidth, height: innerHeight,
  };
}"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _page(browser, size):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": size[0], "height": size[1]})
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    return page


def _open_booking(page) -> str:
    """The page of the first open booking of the list, opened as a row will open
    it: with the list's address as its way back."""
    page.goto(LIST)
    pagina_klaar(page)
    html = page.locator("#betalingen-lijst").inner_html()
    booking = re.search(r"/admin/betalingen/([0-9a-f-]{36})/bevestigen", html)
    assert booking, "no open booking in the seeded list"
    address = f"/admin/betalingen/{booking.group(1)}?terug=/admin/betalingen%3Fzicht%3Dopenstaand"
    page.goto(address)
    pagina_klaar(page)
    return address


@pytest.mark.parametrize(
    "size", [(1920, 1080), (1440, 900), (390, 844)], ids=["1920", "1440", "390"]
)
def test_the_page_fits_and_the_head_is_in_view(browser, size):
    page = _page(browser, size)
    _open_booking(page)
    g = page.evaluate(_GEOMETRY)
    print("MEASURE", size[0], g)
    page.close()

    assert g["scroll"] == g["width"], "the page is wider than the screen"
    assert g["heads"] == 1 and g["shells"] == 1
    for part in ("back", "title", "badges", "figures"):
        assert g[part] and g[part]["y"] + g[part]["h"] <= g["height"], f"{part} is not in view"
    assert g["back"]["y"] < g["title"]["y"], "the way back stands above the title"
    assert g["controls"], "FINANCE sees Bevestig on an open booking"
    if size[0] < 768:
        # The title first: at the left edge, and never squeezed narrower than the
        # controls beside it.
        assert g["title"]["x"] == g["back"]["x"]
        assert g["controls"]["y"] >= g["title"]["y"]
    else:
        assert g["controls"]["x"] > g["title"]["x"] + g["title"]["w"] - 1
    assert g["edit"], "the edit form is not on the page"


def test_a_save_on_the_page_answers_with_the_page(browser):
    page = _page(browser, (1440, 900))
    address = _open_booking(page)
    before = page.locator("#bk-note").input_value()
    note = "e2e-notitie 1574"
    try:
        page.locator("#bk-note").fill(note)
        with page.expect_response(
            lambda r: r.request.method == "POST" and r.url.endswith("/bewerken")
        ):
            page.locator("[data-booking-edit] button[type=submit]").click()
        pagina_klaar(page)

        g = page.evaluate(_GEOMETRY)
        assert g["heads"] == 1 and g["shells"] == 1, f"the page nested or lost its head: {g}"
        assert note in page.locator("[data-booking-figures]").inner_text()
        assert toasts(page).count() >= 1, "no confirmation after the save"
        assert page.url.endswith(address), "the address changed with the save"
        assert page.locator("[data-way-back]").get_attribute("href") == LIST
    finally:
        page.goto(address)
        pagina_klaar(page)
        page.locator("#bk-note").fill(before)
        with page.expect_response(
            lambda r: r.request.method == "POST" and r.url.endswith("/bewerken")
        ):
            page.locator("[data-booking-edit] button[type=submit]").click()
        pagina_klaar(page)
        page.close()
