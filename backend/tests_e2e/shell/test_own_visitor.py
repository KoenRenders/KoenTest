"""E2E: every browser test is a visitor of its own (#1787).

The sign-in forms take five sends a minute per visitor address
(`login_limiter`), counted in the one backend all browser tests share. While
every test came from one address, a test that signs in through the form was
refused whenever the tests before it had used the minute up: its form came back
with the limiter's refusal instead of the code step, and it waited thirty seconds
for a field that never came (`Page.wait_for_selector: Timeout` — seen on
`shell/test_admin_link_after_sign_in.py` and, before it, on
`members/test_sign_in_returns_to_the_portal.py`).

What is shown here, every time:
- the limiter used up on purpose, from an address of this test's own, and what
  the sign-in screen then says;
- a second visitor signing in at that same moment, untouched by it;
- two tests never sharing an address.

Proven red (8 October 2026), three runs: the header no longer added by the
`own_visitor` fixture → the first test uses the minute of the SHARED address up,
`test_admin_link_after_sign_in` right after it fails as it did on `master`
(`Page.wait_for_selector: Timeout`, the code step never comes), and the last test
fails on a request without the address.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

#: What a visitor reads when the limiter refuses (429): the public shell's own
#: sentence for a brake, shown as a toast (#920) — the form itself stays as it was.
REFUSAL = "Je gaat sneller dan de server verwerkt"
LIMIT = 5


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _send(page, email: str) -> tuple[int, str]:
    """Send the e-mail step of the sign-in screen: the status of the answer and
    what the page then shows."""
    page.goto("/aanmelden")
    pagina_klaar(page)
    page.fill("input[name=email]", email)
    with page.expect_response(
        lambda r: r.url.endswith("/aanmelden") and r.request.method == "POST"
    ) as answer:
        page.get_by_role("button", name="Stuur inloginfo").click()
    pagina_klaar(page)
    return answer.value.status, page.locator("body").inner_text()


def test_a_used_up_minute_refuses_its_own_visitor_and_nobody_else(browser, own_visitor):
    mine = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    other = browser.new_page(
        base_url=BASE,
        viewport={"width": 390, "height": 844},
        extra_http_headers={"X-Forwarded-For": "192.0.2.254"},
    )
    try:
        for send in range(LIMIT):
            status, shown = _send(mine, f"niemand-{send}@example.org")
            assert status == 200 and REFUSAL not in shown, f"refused at send {send + 1} of {LIMIT}"
        # The sixth from the same address: this is what the failed tests met — the
        # code step never comes, the form stays, and the shell says why.
        status, shown = _send(mine, "niemand-6@example.org")
        assert status == 429, f"the sixth send answered {status}"
        assert mine.locator("input[name=code]").count() == 0, "a refused send reached the code step"
        assert REFUSAL in shown, f"the visitor is not told; the page shows: {shown[-300:]}"

        # Another visitor, at the same moment.
        status, shown = _send(other, "niemand-anders@example.org")
        assert status == 200, "the limiter refused a visitor from another address"
        assert other.locator("input[name=code]").count() == 1
    finally:
        mine.close()
        other.close()


_seen: list[str] = []


@pytest.mark.parametrize("turn", [1, 2])
def test_two_tests_never_share_an_address(browser, own_visitor, turn):
    """The fixture hands every test another address, and the browser sends it."""
    page = browser.new_page(base_url=BASE)
    try:
        with page.expect_request(lambda r: r.url.endswith("/aanmelden")) as caught:
            page.goto("/aanmelden")
        assert caught.value.headers.get("x-forwarded-for") == own_visitor
    finally:
        page.close()
    assert own_visitor not in _seen, f"{own_visitor} was handed out twice: {_seen}"
    _seen.append(own_visitor)
