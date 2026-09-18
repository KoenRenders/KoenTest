"""E2E: the tenant's header colour survives a boosted navigation (#992).

The trap is #726: htmx puts the server's attributes back on an element with an
`id` after a swap. The colour therefore sits on the <nav>, which has no id and is
never swapped out of band, and not on `#site-nav-mobiel`, which is. Only a
browser shows whether the colour is still there after a click, and whether the
opened mobile menu sits on the same colour.

Waits on Playwright's own conditions (`to_have_css`, `wait_for_url`), not on a
fixed time — see #997.

Broken to see it red (measured): the `style` removed from the <nav> in
`site_base.html` → the first assertion fails.
"""
import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE  # noqa: E402

TELEFOON = {"width": 390, "height": 800}
GROEN = "rgb(0, 93, 41)"


def _zet_kleur(waarde):
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.kernel.tenancy import DEFAULT_TENANT_ID
    from app.kernel.tenant_config import SITE_HEADER_COLOR_KEY, set_setting

    db = SessionLocal()
    try:
        set_setting(db, SITE_HEADER_COLOR_KEY, waarde, tenant_id=DEFAULT_TENANT_ID)
        db.commit()
    finally:
        db.close()


@pytest.fixture
def groene_kop():
    _zet_kleur("#005d29")
    yield
    _zet_kleur(None)


def test_de_kopkleur_blijft_na_navigeren_en_in_het_mobiele_menu(groene_kop):
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        try:
            page = browser.new_page(base_url=BASE, viewport=TELEFOON)
            page.goto("/")
            kop = page.locator("header nav")
            expect(kop).to_have_css("background-color", GROEN)

            # A boosted navigation: #site-nav-mobiel comes along out of band.
            page.evaluate("document.querySelector('#site-nav-breed a[href$=\"/fotos\"]').click()")
            page.wait_for_url("**/fotos")
            expect(page.locator("#site-nav-mobiel")).to_be_hidden()
            expect(kop).to_have_css("background-color", GROEN)

            page.get_by_role("button", name="Menu").click()
            menu = page.locator("#site-nav-mobiel")
            expect(menu).to_be_visible()
            # The menu has no background of its own: what you see is the nav's.
            expect(menu).to_have_css("background-color", "rgba(0, 0, 0, 0)")
            expect(kop).to_have_css("background-color", GROEN)
        finally:
            browser.close()
