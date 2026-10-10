"""E2E #1831 — a meeting without a date says why it is refused.

The route test (`meetings/tests/test_meeting_date_says_why_1831.py`) holds the
answer; this file holds what only a browser can: that the sentence is **on the
screen, in view**, at 390 px, on the form the board was on.

A browser stops an empty date itself (`required`). To send what gets past that
check the test takes `required` off the input — the one thing here a visitor's
browser would not do by itself — and presses "Vergadering aanmaken".

Set `E2E_PRINTS` to a folder to keep a print (outside the repository).

Proven red (locally, restored): the route's `meeting_date` back to `Form(...)`
→ the banner never comes.
"""

from __future__ import annotations

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SENTENCE = "Vul een geldige datum in."


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


def test_a_new_meeting_without_a_date_says_so_on_the_form(page):
    page.goto("/admin/vergaderingen/nieuw")
    pagina_klaar(page)
    page.eval_on_selector("#vg-datum", "el => el.removeAttribute('required')")
    page.locator("#vg-datum").fill("")

    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/admin/vergaderingen")
    ) as answered:
        page.get_by_role("button", name="Vergadering aanmaken").first.click()

    assert answered.value.status == 200
    # The shell boosts this post and swaps the page with a transition: measure
    # the page that stands, not the two that cross.
    pagina_klaar(page)
    page.wait_for_function("() => document.getAnimations().every(a => a.playState !== 'running')")
    banner = page.locator('[role="alert"]').filter(has_text=SENTENCE)
    expect(banner).to_be_visible()
    expect(page.locator('[role="alert"]')).to_have_count(1)
    box = banner.bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= 844, f"the banner is out of view: {box}"
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390, f"the banner is cut off: {box}"
    sideways = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert sideways <= 0, f"the page scrolls sideways by {sideways} px"
    # Still the form of a new meeting, to try again.
    expect(page.locator("#vg-datum")).to_be_visible()
    expect(page.get_by_role("button", name="Vergadering aanmaken").first).to_be_visible()

    folder = os.environ.get("E2E_PRINTS")
    if folder:
        page.screenshot(path=os.path.join(folder, "vergadering-390.png"))
    print(f"\nMEASURED banner {box}, sideways {sideways}")
