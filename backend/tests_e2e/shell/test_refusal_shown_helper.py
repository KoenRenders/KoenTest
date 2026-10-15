"""E2E: `refusal_shown` returns only when the kit's refusal is complete (#1910).

The kit shows a refusal in two steps: the banner, and one settle later the reason
at the refused field with the focus moved to it. A test that types after the
banner alone can cross that move. `schermen.refusal_shown` waits for the second
step; these tests run it on a bare page whose second step comes 400 ms after the
banner, as `record-form.js` does (`link.raakTarget` set, then the focus), so the
result does not depend on the speed of the machine.

Proven red (14 October 2026, put back): the `wait_for_function` taken out of the
helper (it returns at the banner) -> both cases fail: the focus is not yet on the
field when the helper returns.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import refusal_shown  # noqa: E402

WITH_A_FIELD = """
<input id="other"><input id="refused">
<div id="line"></div>
<script>
  setTimeout(() => {
    document.getElementById('line').innerHTML =
      '<div data-save-refusal tabindex="-1"><a data-error-for="x">reason</a></div>';
    setTimeout(() => {
      const link = document.querySelector('[data-error-for]');
      link.raakTarget = document.getElementById('refused');
      link.raakTarget.focus();
    }, 400);
  }, 50);
</script>"""

WITHOUT_A_FIELD = """
<div id="line"></div>
<script>
  setTimeout(() => {
    document.getElementById('line').innerHTML = '<div data-save-refusal tabindex="-1">no field</div>';
    setTimeout(() => document.querySelector('[data-save-refusal]').focus(), 400);
  }, 50);
</script>"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def test_it_waits_for_the_reason_and_the_focus_at_the_refused_field(browser):
    page = browser.new_page()
    page.set_content(WITH_A_FIELD)

    refusal_shown(page)

    assert page.evaluate("document.activeElement.id") == "refused"
    page.close()


def test_it_waits_for_the_focus_on_a_banner_that_names_no_field(browser):
    page = browser.new_page()
    page.set_content(WITHOUT_A_FIELD)

    refusal_shown(page)

    assert page.evaluate("document.activeElement.hasAttribute('data-save-refusal')")
    page.close()
