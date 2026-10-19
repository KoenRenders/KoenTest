"""E2E: Verwijderen where the norm puts it (#2172), at 390 px.

Walked in the browser:

- Pagina's: *Verwijderen* stands last and red in the row's ⋯ and asks the record's
  question; confirmed, the page leaves the list. A section with pages under it answers
  the record's refusal on the list's banner, and stays.
- Organisaties (the platform's record): *Verwijderen* is not under *Acties* while
  reading; in edit mode it stands at the left of the action bar. An organisation a
  tenant names refuses with the tenants' names on the record's banner; an unused one
  is deleted and the browser lands on the list.

The newsletter's and the Design Studio's bar, and the order's *Annuleren*, are walked in
their own files (`test_newsletter_document_page_2113.py`, `test_design_record_2120.py`,
`test_webshop.py`). When `E2E_PRINT_DIR` is set a print of each screen is taken.

Proven red additively (19 October 2026, each put back), on the faster integration tests
of the same rules: `from_list = ""` added in `pagina_verwijderen` → the refusal lands on
the record (`test_from_the_lists_menu_…` in `test_menu_sections_2024.py`);
`deletable = False` added in `_record_view` → the edit bar has no Verwijderen
(`test_organisations_delete_cr20.py`); a delete item added back under the newsletter's
and the design's Acties → their e2e's `count() == 0` is red.

Rows are made for this file (tagged `Weg2172`) and stay: the e2e database is fresh per run.
The example tenant shows the used organisation during this module only; the fixture puts
its own organisation back, since later files read the site's name from it.
"""

import os
import re
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (  # noqa: E402
    BASE,
    PLATFORM,
    htmx_afgerond,
    login_met_sessie,
    pagina_klaar,
)

TAG = "Weg2172"
WIDTH = 390


def _seed() -> dict:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.models import User, UserRole
    from app.domains.cms.api import create_page
    from app.domains.mdm.api import Tenant, create_organization
    from app.kernel.tenancy import TENANT_VOORBEELD_ID
    from app.schemas.cms import CmsPageCreate

    db = SessionLocal()
    try:
        made: dict = {}
        # A second walk on the same database (the prints) needs addresses of its own.
        run = secrets.token_hex(3)
        plain = create_page(db, CmsPageCreate(title=f"{TAG} Los", slug=f"weg2172-los-{run}"))
        section = create_page(
            db, CmsPageCreate(title=f"{TAG} Sectie", slug=f"weg2172-sectie-{run}")
        )
        under = create_page(
            db, CmsPageCreate(title=f"{TAG} Eronder", slug=f"weg2172-eronder-{run}")
        )
        under.parent_id = section.id
        made.update(plain=plain.id, section=section.id)

        used = create_organization(db, name=f"{TAG} In Gebruik vzw")
        unused = create_organization(db, name=f"{TAG} Ongebruikt vzw")
        voorbeeld = db.get(Tenant, TENANT_VOORBEELD_ID)
        # Put back after the module: the other files read the site's name from it.
        made["shown_before"] = voorbeeld.organization_id
        voorbeeld.organization_id = used.id
        made.update(used=used.id, unused=unused.id)

        email = f"e2e-2172-{secrets.token_hex(3)}@example.org"
        user = User(email=email, is_active=True)
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db.commit()
        made["operator"] = email
        return made
    finally:
        db.close()


@pytest.fixture(scope="module")
def world():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    made = _seed()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield {
            "browser": browser,
            "admin": make_session_value(SEEDED_ADMIN_EMAIL),
            "operator": make_session_value(made["operator"]),
            "made": made,
        }
        browser.close()
    _put_back(made["shown_before"])


def _put_back(organization_id) -> None:
    from app.database import SessionLocal
    from app.domains.mdm.api import Tenant
    from app.kernel.tenancy import TENANT_VOORBEELD_ID

    db = SessionLocal()
    try:
        db.get(Tenant, TENANT_VOORBEELD_ID).organization_id = organization_id
        db.commit()
    finally:
        db.close()


def _open(world, path: str, *, platform: bool = False):
    base = PLATFORM if platform else BASE
    page = world["browser"].new_page(base_url=base, viewport={"width": WIDTH, "height": 844})
    login_met_sessie(page, world["operator" if platform else "admin"], base)
    page.goto(path)
    pagina_klaar(page)
    return page


def _print(page, name: str) -> None:
    folder = os.environ.get("E2E_PRINT_DIR")
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    height = page.evaluate("document.documentElement.scrollHeight")
    page.set_viewport_size({"width": WIDTH, "height": max(844, min(height, 3600))})
    page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    page.screenshot(path=os.path.join(folder, f"{name}-{WIDTH}.png"), caret="initial")
    page.set_viewport_size({"width": WIDTH, "height": 844})


def _row(page, page_id: int):
    return page.locator(f'tr[data-row][data-page="{page_id}"]')


def _menu_delete(page, page_id: int):
    row = _row(page, page_id)
    row.locator("[data-row-menu-trigger]").click()
    menu = row.locator("[data-row-menu]")
    expect(menu).to_be_visible()
    items = [t.strip() for t in menu.get_by_role("menuitem").all_inner_texts()]
    assert items[-1] == "Verwijderen", items
    return menu


def test_pages_delete_from_the_rows_menu(world):
    made = world["made"]
    page = _open(world, f"/admin/paginas?q={TAG}")
    try:
        assert page.evaluate("document.documentElement.scrollWidth") == WIDTH
        menu = _menu_delete(page, made["plain"])
        _print(page, "paginas-menu")
        menu.get_by_role("menuitem", name="Verwijderen").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_contain_text(f"“{TAG} Los” definitief verwijderen?")
        with htmx_afgerond(page):
            dialog.get_by_role("button", name="Definitief verwijderen").click()
        expect(_row(page, made["plain"])).to_have_count(0)
        expect(page).to_have_url(re.compile(r"/admin/paginas"))
    finally:
        page.close()


def test_pages_a_section_with_pages_under_it_refuses_on_the_lists_banner(world):
    made = world["made"]
    page = _open(world, f"/admin/paginas?q={TAG}")
    try:
        menu = _menu_delete(page, made["section"])
        menu.get_by_role("menuitem", name="Verwijderen").click()
        with htmx_afgerond(page):
            page.get_by_role("dialog").get_by_role("button", name="Definitief verwijderen").click()
        banner = page.locator("#cp-lijst [role=alert]")
        expect(banner).to_contain_text(f"Er staan nog pagina's onder “{TAG} Sectie”")
        expect(_row(page, made["section"])).to_have_count(1)
        assert page.locator("[data-list-head] h1").inner_text().strip() == "Pagina's"
        _print(page, "paginas-geweigerd")
    finally:
        page.close()


def test_organisation_delete_is_in_the_edit_bar_only(world):
    made = world["made"]
    page = _open(world, f"/admin/organisaties/{made['unused']}", platform=True)
    try:
        trigger = page.locator("[data-actions-trigger]")
        if trigger.count():
            trigger.click()
            assert page.locator("[data-actions-menu]").get_by_text("Verwijderen").count() == 0
        assert page.locator("[data-form-delete]").count() == 0, "not while reading"

        page.goto(f"/admin/organisaties/{made['unused']}?bewerken=1")
        pagina_klaar(page)
        delete = page.locator("[data-action-bar] [data-form-delete]")
        expect(delete).to_have_text("Verwijderen")
        assert page.evaluate("document.documentElement.scrollWidth") == WIDTH
        _print(page, "organisatie-bewerken")
        delete.click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_contain_text("De organisatie en haar gegevens verdwijnen uit de lijsten.")
        dialog.get_by_role("button", name="Definitief verwijderen").click()
        expect(page).to_have_url(re.compile(r"/admin/organisaties$"))
    finally:
        page.close()


def test_organisation_a_tenant_names_refuses_with_the_tenants_names(world):
    from app.database import SessionLocal
    from app.kernel.tenancy import TENANT_VOORBEELD_ID
    from app.kernel.tenant_config import tenant_display_name

    db = SessionLocal()
    try:
        name = tenant_display_name(db, TENANT_VOORBEELD_ID)
    finally:
        db.close()
    made = world["made"]
    page = _open(world, f"/admin/organisaties/{made['used']}?bewerken=1", platform=True)
    try:
        with htmx_afgerond(page):
            page.locator("[data-action-bar] [data-form-delete]").click()
            page.get_by_role("dialog").get_by_role("button", name="Definitief verwijderen").click()
        expect(page.locator("#org-melding")).to_contain_text(name)
        expect(page).to_have_url(re.compile(rf"/admin/organisaties/{made['used']}"))
    finally:
        page.close()
