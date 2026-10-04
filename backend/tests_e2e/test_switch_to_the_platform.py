"""E2E: "Werkruimte wisselen" → Platform lands on the platform (#1536).

On a platform host the `raak_tenant` cookie wins over the platform tenant
(`resolve_request`), and a visit through a department's path prefix sets that
cookie (#889). The switcher linked the platform to the bare host, so a browser
that had been in Raak Millegem landed back in Raak Millegem, with its full menu.
Measured on HDEV by Koen while testing #1523.

The test runs on the e2e platform host, as HDEV does: visit `/raakmillegem/admin`,
switch to the platform, and the sidebar names the platform and shows only its
modules; switch back, and Raak Millegem's full menu returns.

Red against master `78555830`: after the switch the sidebar still said
"Raak Millegem" and held /admin/activiteiten.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import PLATFORM, pagina_klaar  # noqa: E402

_SIDEBAR = """() => ({
  name: document.querySelector('#admin-zijbalk .admin-sidebar-brand .nav-label').textContent.trim(),
  hrefs: [...document.querySelectorAll('#admin-nav-zijbalk a')].map(a => a.getAttribute('href')),
})"""


@pytest.fixture(scope="module")
def page():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(viewport={"width": 1440, "height": 900})
        p.context.add_cookies(
            [
                {
                    "name": "raak_session",
                    "value": make_session_value(SEEDED_ADMIN_EMAIL),
                    "url": PLATFORM,
                }
            ]
        )
        yield p
        browser.close()


def _switch(page, name: str) -> dict:
    page.goto(PLATFORM + "/admin/werkruimte-wisselen")
    pagina_klaar(page)
    page.locator("#main a").filter(has_text=name).first.click()
    page.wait_for_url("**/admin")
    pagina_klaar(page)
    return page.evaluate(_SIDEBAR)


def test_switching_to_the_platform_lands_on_the_platform_and_back(page):
    page.goto(PLATFORM + "/raakmillegem/admin")
    pagina_klaar(page)
    before = page.evaluate(_SIDEBAR)
    assert before["name"] == "Raak Millegem"
    assert "/admin/activiteiten" in before["hrefs"]
    assert any(c["name"] == "raak_tenant" for c in page.context.cookies(PLATFORM)), (
        "the prefix visit set the cookie that used to win"
    )

    on_platform = _switch(page, "Digital Platform")
    print("MEASURE platform", on_platform)
    assert on_platform["name"] == "Digital Platform"
    assert "/admin/paginas" in on_platform["hrefs"]
    for off in ("/admin/activiteiten", "/admin/leden", "/admin/vergaderingen"):
        assert off not in on_platform["hrefs"], off

    back = _switch(page, "Raak Millegem")
    print("MEASURE back", back)
    assert back["name"] == "Raak Millegem"
    assert "/admin/activiteiten" in back["hrefs"]
