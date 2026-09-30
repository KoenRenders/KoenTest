"""E2E: the mobile admin menu carries the account items of the desktop menu (#1381).

At 390 px the menu behind the hamburger had only "Naar de site" and "Uitloggen",
so on a phone an admin could not open their profile or switch workspace. The
mobile menu now loads the same partial as the desktop menu, lazily, with the same
rule: "Werkruimte wisselen" only for an account with roles in more than one
workspace. Every account item is a 44 px touch target, and the page stays as wide
as the viewport.

Proven red against master `08a3ffbd` (served from an export of it): the menu of
the account with two workspaces had no "Mijn profiel" and no "Werkruimte
wisselen". The first build loaded the items on `intersect` against the viewport,
and at 900 px the block sat below the fold: nothing loaded until a scroll. It is
measured against the menu now (`root:#admin-nav-mobiel`).
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (  # noqa: E402
    BASE,
    login_met_sessie,
    netwerk_bijgewerkt,
    pagina_klaar,
)

SHOTS = "/scratch/shots_1381"
PHONE = {"width": 390, "height": 900}

_MEASURE = """() => {
  const menu = document.getElementById('admin-nav-mobiel');
  const items = [...menu.querySelectorAll('a')].filter(a => a.offsetHeight)
    .map(a => ({text: a.textContent.trim(), height: a.getBoundingClientRect().height}));
  return {items, doc: document.documentElement.scrollWidth, vw: innerWidth};
}"""


def _account(*tenants: int) -> str:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import User, UserRole

    email = f"menu-{secrets.token_hex(3)}@example.com"
    db = SessionLocal()
    try:
        user = User(email=email, is_active=True)
        db.add(user)
        db.flush()
        for tenant in tenants:
            db.add(UserRole(user_id=user.id, role_code="ADMIN", tenant_id=tenant))
        db.commit()
    finally:
        db.close()
    return email


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _open_menu(browser, email: str, shot: str) -> dict:
    from app.domains.auth.api import make_session_value

    page = browser.new_page(base_url=BASE, viewport=PHONE)
    try:
        login_met_sessie(page, make_session_value(email))
        page.goto("/admin")
        pagina_klaar(page)
        page.get_by_role("button", name="Menu").click()
        page.locator("#admin-nav-mobiel").wait_for(state="visible")
        # The intersect observer reports in the frame after the menu shows; then
        # the barrier waits until whatever it started is answered and swapped. On
        # master nothing starts, and the assertions below say what is missing.
        page.evaluate(
            "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
        )
        netwerk_bijgewerkt(page)
        measured = page.evaluate(_MEASURE)
        print("MEASURE", shot, measured)
        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.locator("#admin-nav-mobiel a", has_text="Uitloggen").scroll_into_view_if_needed()
            page.wait_for_function(
                "() => document.getAnimations().every(a => a.playState !== 'running')"
            )
            page.evaluate(
                "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
            )
            page.screenshot(path=f"{SHOTS}/390-{shot}.png")
        return measured
    finally:
        page.close()


def test_two_workspaces_show_the_switch_in_the_mobile_menu(browser):
    from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID

    measured = _open_menu(browser, _account(TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID), "two")
    texts = [i["text"] for i in measured["items"]]
    assert "Mijn profiel" in texts, measured
    assert "Werkruimte wisselen" in texts, measured
    assert "Uitloggen" in texts, measured
    account = [
        i
        for i in measured["items"]
        if i["text"] in ("Mijn profiel", "Werkruimte wisselen", "Uitloggen")
    ]
    assert len(account) == 3, f"each account item once: {measured}"
    assert all(i["height"] >= 44 for i in account), f"a touch target under 44 px: {account}"
    assert measured["doc"] <= measured["vw"], measured


def test_one_workspace_has_no_switch_in_the_mobile_menu(browser):
    from app.kernel.tenancy import TENANT_MILLEGEM_ID

    measured = _open_menu(browser, _account(TENANT_MILLEGEM_ID), "one")
    texts = [i["text"] for i in measured["items"]]
    assert "Mijn profiel" in texts and "Uitloggen" in texts, measured
    assert "Werkruimte wisselen" not in texts, measured
