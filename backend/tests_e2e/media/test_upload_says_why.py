"""E2E #1831 — the media upload says why it refuses a post without a file.

The route test (`media/tests/test_upload_says_why_1831.py`) holds the answer; this
file holds what only a browser can: that the sentence is **on the screen, in
view**, at 390 px, and not the kit's general message.

A browser stops an empty file input itself (`required`). To send what gets past
that check the test takes `required` off the input — the one thing here a
visitor's browser would not do by itself — and presses "Uploaden".

Set `E2E_PRINTS` to a folder to keep a print (outside the repository).

Proven red (locally, restored): the route's `files` back to `File(...)` → the
banner never comes, and the general message does.
"""

from __future__ import annotations

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

NO_FILE = "Geen bestanden"
GENERAL = "Er ging iets mis"


@pytest.fixture(scope="module")
def page():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    session = make_session_value(os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL)
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
        login_met_sessie(page, session)
        yield page
        browser.close()


def test_an_upload_without_a_file_says_so_on_the_page(page):
    page.goto("/admin/media/nieuw?kind=sponsor")
    pagina_klaar(page)
    page.eval_on_selector("#me-files", "el => el.removeAttribute('required')")

    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/admin/media")
    ) as answered:
        page.get_by_role("button", name="Uploaden").first.click()

    assert answered.value.status == 200
    banner = page.locator('[role="alert"]').filter(has_text=NO_FILE)
    expect(banner).to_be_visible()
    box = banner.bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= 844, f"the banner is out of view: {box}"
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390, f"the banner is cut off: {box}"
    sideways = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert sideways <= 0, f"the page scrolls sideways by {sideways} px"
    expect(page.get_by_text(GENERAL)).to_have_count(0)
    # Still the upload page, with the kind that was chosen and its form to try again.
    assert page.locator("#me-kind").input_value() == "sponsor"
    expect(page.locator("#me-files")).to_be_visible()

    folder = os.environ.get("E2E_PRINTS")
    if folder:
        page.screenshot(path=os.path.join(folder, "upload-390.png"))
    print(f"\nMEASURED banner {box}, sideways {sideways}")
