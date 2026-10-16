"""E2E: the account page's menu is the menu under the visitor's name (#1886).

Koen, 10 October 2026: the menu on the left of an account page listed the
account pages only, where the menu under his first name in the header carries
"Admin" and "Uitloggen" too — "ik bedoel het menu aan de linkerkant, dat moet
gelijk zijn aan mijn uitklapmenu op de publieke site". Since #1886 the left menu
and "Meer in je account" render the shell's one list (`_site_account.items`).

Read on a wide screen for the same visitor, once without and once with a way
into the back office: the labels and the addresses of the left menu equal those
of the header's menu, in the same order; "Uitloggen" stands once in the left
menu and leaves the session with a full navigation, as in the header.

Set `E2E_PRINTS` to a folder to keep prints of the account page at 1440 and
390 px (outside the repository).

Red on master `ce218671` (15 October 2026): the left menu reads the four pages
and the header's menu the four pages and Uitloggen (and Admin with the role),
so both cases fail on the comparison.
"""

from __future__ import annotations

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

READ = """(scope) => [...document.querySelectorAll(scope + ' a[data-account-item]')].map(a => ({
  label: a.textContent.trim(), href: a.getAttribute('href'), kind: a.dataset.accountItem,
  boost: a.getAttribute('hx-boost'), current: a.getAttribute('aria-current')}))"""


def _db():
    import app.main  # noqa: F401  the whole app, so the domain facades import in order
    from app.database import SessionLocal

    return SessionLocal()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def board_role():
    """The seeded member, given the role ADMIN for one test and stripped of it
    after: a member with a way into the back office."""
    from app.domains.auth.api import User, UserRole
    from seed_e2e import MARKER_EMAIL

    db = _db()
    try:
        user = db.query(User).filter(User.email == MARKER_EMAIL).first()
        made = user is None
        if made:
            user = User(email=MARKER_EMAIL, is_active=True)
            db.add(user)
            db.flush()
        role = UserRole(user_id=user.id, role_code="ADMIN")
        db.add(role)
        db.commit()
        ids = (user.id, made)
    finally:
        db.close()
    yield
    db = _db()
    try:
        user_id, made = ids
        db.query(UserRole).filter(
            UserRole.user_id == user_id, UserRole.role_code == "ADMIN"
        ).delete(synchronize_session=False)
        if made:
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _page(browser, width: int):
    from app.domains.auth.api import make_session_value
    from seed_e2e import MARKER_EMAIL

    page = browser.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    login_met_sessie(page, make_session_value(MARKER_EMAIL), BASE)
    return page


def _compare(browser, *, admin: bool) -> None:
    page = _page(browser, 1440)
    try:
        page.goto("/mijn")
        pagina_klaar(page)
        page.locator("[data-account-button]").click()
        page.locator("[data-account-menu]").wait_for(state="visible")
        header = page.evaluate(READ, "[data-account-menu]")
        left = page.evaluate(READ, "[data-account-page-menu]")
        print("MEASURE header", header, "left", left)
        assert [(i["label"], i["href"]) for i in left] == [
            (i["label"], i["href"]) for i in header
        ], (left, header)
        kinds = [i["kind"] for i in left]
        assert kinds.count("sign-out") == 1 and kinds[-1] == "sign-out", kinds
        assert kinds.count("admin") == (1 if admin else 0), kinds
        assert all(i["boost"] == "false" for i in left if i["kind"] != "member"), left
        assert [i["href"] for i in left if i["current"] == "page"] == ["/mijn"], left
    finally:
        page.close()


def test_without_the_back_office_the_left_menu_is_the_header_menu(browser):
    _compare(browser, admin=False)


def test_with_the_back_office_the_left_menu_is_the_header_menu(browser, board_role):
    _compare(browser, admin=True)


@pytest.mark.parametrize("width", [390, 1440])
def test_the_account_page_with_its_one_menu(browser, board_role, width):
    """Below 1 088 px the menu is not on the page and "Meer in je account"
    carries the same list at its bottom, the page marked; neither may push the
    page wider than the window."""
    page = _page(browser, width)
    try:
        page.goto("/mijn")
        pagina_klaar(page)
        scope = "[data-account-links]" if width < 1088 else "[data-account-page-menu]"
        shown = page.locator(scope)
        assert shown.is_visible(), scope
        rows = page.evaluate(READ, scope)
        assert [i["kind"] for i in rows][-2:] == ["admin", "sign-out"], rows
        assert [i["href"] for i in rows if i["current"] == "page"] == ["/mijn"], rows
        scroll, inner = page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
        assert scroll <= inner, (scroll, inner)
        folder = os.environ.get("E2E_PRINTS")
        if folder:
            os.makedirs(folder, exist_ok=True)
            page.screenshot(path=os.path.join(folder, f"1886-mijn-{width}.png"), full_page=True)
    finally:
        page.close()
