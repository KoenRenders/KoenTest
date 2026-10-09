"""E2E CR-24 slice 5 (#1722) — the back office by right, as a user sees it at 390 px.

What only a browser shows: the way from the public site into the back office,
where it comes out, and the menu a user with one role sees there.

- **Boekhouding alone** (FINANCE) and **Masterdata alone**: the site's menu has
  the item Admin; it leads to the workbench (Q13, Q16); the back office's menu
  holds exactly the screens whose right the role bundles, each of them opens,
  and a screen outside it is refused. Until CR-24 a FINANCE-only user had one
  hand-made menu with Betalingen alone and could not open the workbench, and
  Masterdata did not exist.
- **Beheer › Gebruikers**: a role is ticked by its label — Beheerder,
  Boekhouding, Masterdata, … — and no role code stands on the screen.

Measured from the rendered DOM: the menu's items as they are shown, and that the
page does not scroll sideways with the menu open.

Set `E2E_PRINTS` to a folder to keep the prints (outside the repository).

Proven red (locally, restored): the condition that asks the viewer's rights taken
out of the menu (`nav_for`) → both role tests fail on the menu shown: Werkbank,
Activiteiten, Leden, Formulieren, … where two and four items are wanted.
"""

from __future__ import annotations

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

WORKBENCH = "/admin/werkbank"

#: Per role: the label on screen, and the menu its bundle gives — in the menu's order.
MENUS = {
    "FINANCE": ("boekhouding", ["Werkbank", "Betalingen"]),
    "MASTERDATA": ("masterdata", ["Werkbank", "Leden", "Personen", "Onze organisatie"]),
}

#: The roles to tick in a tenant's workspace, as the screen names them.
LABELS = [
    "Beheerder",
    "Boekhouding",
    "Accountbeheerder",
    "Masterdata",
    "Prijsbeheer",
    "Verkoop",
    "Voorraadbeheer",
]
CODES = ["ADMIN", "FINANCE", "ACCOUNT_ADMIN", "MASTERDATA", "PRICING", "SALES", "STOCK", "OPERATOR"]


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def sessions():
    """One user per role, each holding that role alone in the association's workspace."""
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole

    db = SessionLocal()
    out = {}
    for role in ("FINANCE", "MASTERDATA", "ADMIN"):
        email = f"e2e-1722-{role.lower()}-{secrets.token_hex(3)}@example.org"
        user = User(email=email, is_active=True)
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_code=role))
        out[role] = make_session_value(email)
    db.commit()
    db.close()
    return out


@pytest.fixture
def page(browser):
    p = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    yield p
    p.close()


def _print(page, name: str) -> None:
    prints = os.environ.get("E2E_PRINTS")
    if prints:
        page.screenshot(path=os.path.join(prints, f"{name}-390.png"))


def _sideways(page) -> int:
    return page.evaluate("() => document.documentElement.scrollWidth - innerWidth")


@pytest.mark.parametrize("role", sorted(MENUS))
def test_one_role_enters_by_the_workbench_and_sees_its_own_menu(page, sessions, role):
    name, menu = MENUS[role]
    login_met_sessie(page, sessions[role])

    # From the public site: the menu's Admin item, and where it leads.
    page.goto(BASE + "/")
    pagina_klaar(page)
    page.locator("[data-menu-button]").click()
    admin = page.locator('[data-drawer-account] [data-account-item="admin"]')
    expect(admin).to_be_visible()
    assert admin.get_attribute("href") == WORKBENCH
    _print(page, f"site-menu-{name}")
    admin.click()
    page.wait_for_url(f"**{WORKBENCH}")
    pagina_klaar(page)
    title = page.locator("#main h1").first.inner_text().strip()
    print(f"MEASURE {role} lands on {page.url.replace(BASE, '')} | {title}")
    assert title == "Werkbank", title
    _print(page, f"landing-{name}")

    # The back office's menu, as shown.
    page.get_by_role("button", name="Menu", exact=True).click()
    nav = page.locator("#admin-nav-zijbalk")
    expect(nav.locator("a.nav-link").first).to_be_visible()
    shown = [
        (link.get_attribute("aria-label"), link.get_attribute("href"))
        for link in nav.locator("a.nav-link").all()
        if link.is_visible()
    ]
    sideways = _sideways(page)
    print(
        f"MEASURE {role} menu: {len(shown)} items {[label for label, _h in shown]}, sideways {sideways} px"
    )
    _print(page, f"menu-{name}")
    assert [label for label, _href in shown] == menu, shown
    assert sideways == 0, f"the page is {sideways} px wider than the window with the menu open"

    # Every item opens for this user; a screen outside the menu does not.
    answers = {href: page.request.get(BASE + href).status for _label, href in shown}
    assert set(answers.values()) == {200}, f"the menu offers a screen that refuses: {answers}"
    assert page.request.get(BASE + "/admin/activiteiten").status == 403
    assert page.request.get(BASE + "/admin").status == 403, "the start page asks report.view"


def test_gebruikers_ticks_roles_by_their_label(page, sessions):
    login_met_sessie(page, sessions["ADMIN"])
    page.goto(BASE + "/admin/gebruikers")
    pagina_klaar(page)
    row = page.locator("#gu-lijst form").first
    expect(row).to_be_visible()
    labels = [
        t.strip() for t in row.locator('label:has(input[name="role_codes"])').all_inner_texts()
    ]
    text = page.locator("#main").inner_text()
    codes = [code for code in CODES if code in text.split()]
    sideways = _sideways(page)
    print(
        f"MEASURE gebruikers: {len(labels)} roles to tick {labels}, codes on screen {codes}, sideways {sideways} px"
    )
    row.scroll_into_view_if_needed()
    _print(page, "gebruikers-labels")
    assert labels == LABELS, labels
    assert not codes, f"a role code stands on the screen: {codes}"
    assert sideways == 0, f"the page is {sideways} px wider than the window"
