"""E2E #1853 — an e-mail row in Mijn gezin refuses a text that is no address, at the row.

The service tests (`mdm/tests/test_household_save.py`) hold that the refusal is
placed at the row's own field and that nothing is written; this file holds what
only a browser can, at 390 px: the banner names the rule, the row itself is
marked and in view and still holds what was typed, the rest of the form too.

What the browser lets through by itself: `naam@domein` without a dot.

Set `E2E_PRINTS` to a folder to keep a print (outside the repository).

Proven red (locally, restored): the question in `household_save._save_emails`
removed → the refusal no longer stands on the row (no field is marked).
"""

from __future__ import annotations

import os
import sys
import uuid

from playwright.sync_api import expect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.members.test_household_pages import (  # noqa: E402, F401
    HEAD,
    _household,
    _open,
    _remove,
    _session,
    _sign_up,
    browser,
)

RULE = "Vul een geldig e-mailadres in."
NO_DOT = "hoofd@zonderpunt"


def test_a_row_in_mijn_gezin_says_why_at_the_row(browser):  # noqa: F811
    tag = uuid.uuid4().hex[:8]
    email = _sign_up(browser, tag)
    page = _open(browser, "/leden/gezin?bewerken=1", session=_session(email))
    try:
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        head = page.locator(HEAD)
        head.locator("[data-repeating-group] [data-group-add]").click()
        typed = head.locator('input[type="email"]').nth(1)
        typed.fill(NO_DOT)
        page.fill("#address-street", "Blijfstraat")
        page.locator("[data-form-save]").click()

        banner = page.locator("[data-save-refusal]")
        expect(banner).to_contain_text("Opslaan kan nog niet: controleer 1 veld.")
        expect(banner).to_contain_text(RULE)
        # The row itself is marked and holds what was typed; the rest of the form too.
        expect(typed).to_have_attribute("aria-invalid", "true")
        expect(typed).to_have_value(NO_DOT)
        expect(page.locator("#address-street")).to_have_value("Blijfstraat")
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "edit")
        box = typed.bounding_box()
        assert 0 <= box["y"] and box["y"] + box["height"] <= 844, f"the row is out of view: {box}"
        sideways = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert sideways <= 0, f"the page scrolls sideways by {sideways} px"
        folder = os.environ.get("E2E_PRINTS")
        if folder:
            page.screenshot(path=os.path.join(folder, "emailrij-mijn-gezin-390.png"))
        stored = _household(email)
        assert stored["address"][0] == "Teststraat", "a refused save wrote the address"
        print(f"\nMEASURED mijn gezin: row {box}, sideways {sideways}")
    finally:
        page.close()
        _remove(email)
