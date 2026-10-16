"""E2E: Koen's path — make an account, sign in, open Lid worden (#1883).

Koen, 10 October 2026: he made himself an account, signed in and clicked "Lid
worden" — and got an empty form. Since #1883 he stands in it as the main
member: his name, his e-mail address and his mobile as his (read, not typed —
Koen, 15 October 2026: "a"), with where he changes them, and what he still has
to give asked.

Walked in the browser at 390 px: the account is made through "Account
aanmaken" with made-up data on the reserved example domain, the code is entered
(the test sets a known code's hash on the living token, as
`test_create_account.py` does), and Lid worden is opened signed in. Read from
the rendered page: the main member's card shows the name, the address and the
mobile, has no field to type them, and says where they are changed; the page is
no wider than the window, at 390 and at 1 440 px.

Set `E2E_PRINTS` to a folder to keep a print at each width (outside the
repository). The person made is removed again.

Red on master `a825439c` (16 October 2026): the card holds empty fields for the
name and the mobile, and no address.
"""

import os
import sys
import uuid

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.members.test_create_account import (  # noqa: E402
    CODE,
    KEY_DELAY_MS,
    _remove,
    _set_code,
)
from tests_e2e.schermen import BASE, htmx_afgerond, pagina_klaar  # noqa: E402

CARD = """() => { const card = document.querySelector('#hoofdlid');
  const typed = [...card.querySelectorAll('input:not([type=hidden]), select')].map(i => i.name);
  return {text: card.innerText, typed, own: !!card.querySelector('[data-own-details] a[href$="/mijn/gegevens"]'),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _print(page, width: int) -> None:
    folder = os.environ.get("E2E_PRINTS")
    if folder:
        os.makedirs(folder, exist_ok=True)
        page.locator("#hoofdlid").screenshot(
            path=os.path.join(folder, f"1883-hoofdlid-{width}.png")
        )


def test_an_account_opens_lid_worden_and_stands_in_it_as_the_main_member(browser):
    email = f"koen-pad-{uuid.uuid4().hex[:8]}@example.org"
    page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        page.goto("/account-aanmaken")
        pagina_klaar(page)
        form = page.locator("[data-create-account-form]")
        form.locator('input[name="first_name"]').press_sequentially("Petra", delay=KEY_DELAY_MS)
        form.locator('input[name="last_name"]').press_sequentially("Proef", delay=KEY_DELAY_MS)
        form.locator('input[name="email"]').press_sequentially(email, delay=KEY_DELAY_MS)
        form.locator('input[name="mobile"]').press_sequentially("0470 00 18 83", delay=KEY_DELAY_MS)
        with htmx_afgerond(page):
            form.locator("button").click()
        expect(page.locator("[data-code-sent]")).to_be_visible()
        _set_code(email)
        page.locator('input[name="code"]').fill(CODE)
        page.locator("[data-sign-in-step] button").click()
        page.wait_for_url(lambda url: "/account-aanmaken" not in url and "/aanmelden" not in url)

        for width, height in ((390, 844), (1440, 900)):
            page.set_viewport_size({"width": width, "height": height})
            page.goto("/lid-worden")
            pagina_klaar(page)
            card = page.evaluate(CARD)
            print("MEASURE main member", width, card)
            _print(page, width)
            for shown in ("Petra", "Proef", email, "0470 00 18 83"):
                assert shown in card["text"], (width, shown, card["text"])
            for name in ("h.n0.first_name", "h.n0.last_name", "h.n0.mobile"):
                assert name not in card["typed"], (width, name)
            assert not any(n.startswith("e.") for n in card["typed"]), card["typed"]
            assert "h.n0.date_of_birth" in card["typed"] and "h.n0.gender_code" in card["typed"]
            assert card["own"], "the card does not say where his details are changed"
            assert card["page"][0] == card["page"][1], f"wider than the window at {width}"
    finally:
        page.close()
        _remove(email)
