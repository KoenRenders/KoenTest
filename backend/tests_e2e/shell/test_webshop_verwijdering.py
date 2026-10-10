"""E2E CR-21 (#1887) — the refused delete of an article with a movement.

The shop is off by default for every kind of tenant, and a tenant's module set is
cached in the server process, so the browser test runs on a seeded tenant of its
own (`webshop` in `seed_e2e.py`), reached by hostname (`TENANT_HOSTNAMES` in
`e2e.env` — back-office screens are not reached by a path prefix). The
association's tenant stays untouched. The test asks visibility of the refusal —
a box with a size, in view — not the answer's text.
"""

from __future__ import annotations

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import htmx_afgerond, login_met_sessie  # noqa: E402

WEBSHOP_HOST = "http://webshop.localhost:8000"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def webshop_page(browser):
    """A browser signed in as the seeded admin on the seeded shop tenant."""
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=WEBSHOP_HOST)
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), WEBSHOP_HOST)
    page.goto("/admin/producten")
    if page.locator('a[href^="/admin/producten/"]:not([href$="/nieuw"])').count() == 0:
        pytest.fail("geen artikel op de webshop-tenant (seed_e2e)")
    yield page
    page.close()


def test_een_verwijdering_met_voorraad_is_zichtbaar_geweigerd(webshop_page):
    """A delete of an article with a movement is refused in a box the user can
    see (AC19, W23). The browser is the only layer that proves that (#613)."""
    page = webshop_page
    page.locator('a[href^="/admin/producten/"]:not([href$="/nieuw"])').first.click()

    page.get_by_role("button", name="Acties").click()
    item = page.locator('[data-actions-menu] [role=menuitem][hx-post$="/verwijderen"]').first
    item.click()
    ok = page.locator("[data-dialog] [data-dialog-ok]")
    ok.wait_for(state="visible")
    with htmx_afgerond(page):
        ok.click()

    expect(page.locator("#product-melding [role=alert]")).to_be_visible()
