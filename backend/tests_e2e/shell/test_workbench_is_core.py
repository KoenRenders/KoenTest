"""E2E, #1876: the tenant editor offers no switch for the workbench — it is core.

Measured from the rendered DOM at 390 px, on the editor of a tenant in the
platform workspace:

- one card per module that can be switched, each with one checkbox, and none
  of them the workbench's: no checkbox with its code, no card with its name;
- the page does not scroll sideways;
- the workbench itself is in the menu of that same screen — out of the editor
  is not out of the back office.

Set `E2E_PRINTS` to a folder to keep the print (outside the repository).

Proven red (locally, restored): the workbench's entry put back in the module
registry (its code and its entry) → the test fails on the card and the switch
it finds for `workflow`.
"""

from __future__ import annotations

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import PLATFORM, login_met_sessie, pagina_klaar  # noqa: E402

_CARDS = """() => [...document.querySelectorAll('[data-card]')].map(card => ({
  code: card.dataset.card,
  title: (card.querySelector('h2, h3, label') || card).textContent.replace(/\\s+/g, ' ').trim(),
  switches: [...card.querySelectorAll('input[type="checkbox"][name="modules"]')].map(i => i.value),
}))"""

_MENU = """() => [...document.querySelectorAll('#admin-nav-zijbalk a[href]')]
  .map(a => new URL(a.href).pathname)"""


@pytest.fixture(scope="module")
def editor():
    from app.domains.auth.api import make_session_value
    from app.kernel.modules import MODULES
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=PLATFORM, viewport={"width": 390, "height": 844})
        login_met_sessie(page, make_session_value(email), PLATFORM)
        page.goto("/admin/tenants")
        pagina_klaar(page)
        link = page.locator(
            "xpath=//a[starts-with(@href,'/admin/tenants/') and "
            "translate(substring-after(@href,'/admin/tenants/'),'0123456789','')='']"
        ).first
        assert link.count(), "no tenant to edit in the seeded data"
        page.goto(link.get_attribute("href"))
        pagina_klaar(page)
        yield page, {m.code.value: m.label for m in MODULES}
        browser.close()


def test_the_editor_has_no_switch_for_the_workbench(editor):
    page, modules = editor
    cards = page.evaluate(_CARDS)
    switched = {c["code"]: c["switches"] for c in cards if c["code"] != "site"}
    # A platform has no card for members (#854); every other module has one.
    assert set(switched) <= set(modules) and len(switched) >= len(modules) - 1, switched
    assert all(switches == [code] for code, switches in switched.items()), switched
    assert "workflow" not in switched
    assert page.locator('input[name="modules"][value="workflow"]').count() == 0
    assert not [c["title"] for c in cards if "Werkbank" in c["title"]]

    assert page.evaluate("() => document.documentElement.scrollWidth - innerWidth") <= 0
    assert "/admin/werkbank" in page.evaluate(_MENU), "the workbench left the menu too"

    prints = os.environ.get("E2E_PRINTS")
    if prints:
        height = page.evaluate("() => document.documentElement.scrollHeight")
        page.set_viewport_size({"width": 390, "height": height})
        page.screenshot(
            path=os.path.join(prints, "tenant-editor-390.png"),
            clip={"x": 0, "y": 0, "width": 390, "height": height},
        )
        page.set_viewport_size({"width": 390, "height": 844})
