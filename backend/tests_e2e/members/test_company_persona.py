"""E2E, CR-19 C6 test 13 (#1477), first flow: the company persona, end to end —
B2 steps 1–8 on a tenant of kind BEDRIJF.

1. The operator creates the tenant through "Nieuwe tenant", type Bedrijf. Through
   the screen and not in this process: the server's tenant cache is cleared only
   by the process that creates the tenant, and it has no time limit.
2. Its editor ticks exactly Pagina's, Media and Formulieren, and offers no
   switch for the workbench: that is core (#1876).
3. A user with ADMIN in that workspace sees only the menu of those modules and
   the shell's own items.
4. The dashboard shows "Open taken (werkbank)" only.
5. A visitor sees the seeded home text and footer, no membership band, no
   activity cards, and the navigation Home · Aanmelden — plus the page the tenant
   published; the wordmark is its name (#1496).
6. /activiteiten, /lid-worden and /fotos answer "niet gevonden". /fotos is
   Media's route, but the albums are the albums of activities: it asks for both
   (#1477), as its menu item did (#1476).
7. The sitemap lists the home, the published pages and what the modules that are
   on add, nothing of a module that is off. It does hold /berichten, which
   Formulieren adds — a page without a form on a new tenant until #1509.
8. A form of the tenant, linked from a published page, filled in by a visitor,
   shows its submission under Formulieren. Not the task in the Werkbank B2 also
   names: only the contact form makes a task, and a new tenant has none (#1509).

The data the screens cannot make here — the workspace's admin, the form and the
page — is written straight into the database, for that tenant.

Proven red (locally): the media router guarded by Media alone fails step 6 on
/fotos; the sitemap without the menu's rule fails step 7; the form posting to
its bare `form_action` (no `path_for`) fails step 8, whose visitor sends without
the `raak_tenant` cookie.
"""

from __future__ import annotations

import os
import re
import secrets
import sys
from xml.etree import ElementTree

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, PLATFORM, login_met_sessie, pagina_klaar  # noqa: E402

CODE = f"bakker-{secrets.token_hex(3)}"
NAME = f"Bakkerij Peeters {CODE[-6:]}"
COMPANY_MODULES = {"cms", "media", "forms"}

_MENU = """() => [...new Set([...document.querySelectorAll('aside a[href*="/admin"], nav a[href*="/admin"]')]
  .map(a => a.textContent.replace(/\\s+/g, ' ').trim()))]"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def operator() -> str:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import User, UserRole, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    db = SessionLocal()
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not db.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
        db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db.commit()
    db.close()
    return make_session_value(SEEDED_ADMIN_EMAIL)


def _page(browser, session=None, width=1440, base=BASE):
    page = browser.new_page(base_url=base, viewport={"width": width, "height": 1000})
    login_url = base
    if session:
        login_met_sessie(page, session, login_url)
    return page


@pytest.fixture(scope="module")
def company(browser, operator) -> dict:
    """Steps 1 and 2, then the data for 3 and 8: the tenant's id, its admin's
    session, and a form linked from a published page."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import User, UserRole, make_session_value
    from app.domains.cms.api import CmsPage
    from app.domains.forms.models import Form, FormField, FormSection
    from app.domains.mdm.api import Organization

    page = _page(browser, operator, base=PLATFORM)  # #1535: Tenants, on the platform
    page.goto("/admin/tenants/nieuw")
    pagina_klaar(page)
    page.get_by_text("Bedrijf", exact=True).click()
    page.fill("#t-name", NAME)
    page.fill("#t-code", CODE)
    page.get_by_role("button", name="Opslaan").first.click()
    page.wait_for_selector("text=Tenant aangemaakt.")
    listed = page.locator("main").inner_text()
    page.close()

    db = SessionLocal()
    tenant = db.query(Organization).filter(Organization.code == CODE).one()
    admin_email = f"admin-{CODE}@example.org"
    admin = User(email=admin_email, is_active=True)
    db.add(admin)
    db.flush()
    db.add(UserRole(user_id=admin.id, role_code="ADMIN", tenant_id=tenant.id))
    form = Form(
        title="Vraag aan de bakker",
        share_token=f"tok-{secrets.token_hex(8)}",
        status="open",
    )
    form.tenant_id = tenant.id
    db.add(form)
    db.flush()
    section = FormSection(form_id=form.id, title="Je vraag", position=0)
    section.tenant_id = tenant.id
    db.add(section)
    db.flush()
    field = FormField(
        form_id=form.id,
        section_id=section.id,
        field_type="text",
        label="Welk brood?",
        required=True,
        position=0,
    )
    field.tenant_id = tenant.id
    db.add(field)
    db.flush()
    page_row = CmsPage(
        slug="vragen",
        title="Vragen",
        content=f'<p><a href="/{CODE}/formulier/{form.share_token}">Stel je vraag</a></p>',
        is_published=True,
    )
    page_row.tenant_id = tenant.id
    db.add(page_row)
    db.commit()
    out = {
        "id": tenant.id,
        "listed": listed,
        "admin": make_session_value(admin_email),
        "form_id": form.id,
        "field": f"f{field.id}",
    }
    db.close()
    return out


def test_1_the_operator_creates_a_company(company):
    assert NAME in company["listed"] and "Bedrijf" in company["listed"]


def test_2_its_editor_ticks_the_company_modules(browser, operator, company):
    page = _page(browser, operator, base=PLATFORM)  # #1535: Tenants, on the platform
    page.goto(f"/admin/tenants/{company['id']}")
    pagina_klaar(page)
    ticked = set(
        page.eval_on_selector_all(
            'input[type="checkbox"][name="modules"]:checked', "els => els.map(e => e.value)"
        )
    )
    # #1533: the kind is a choice in the editor now, BEDRIJF ticked.
    kind = page.eval_on_selector('input[name="kind"]:checked', "e => e.value")
    page.close()
    assert ticked == COMPANY_MODULES
    assert kind == "BEDRIJF"


def test_3_its_admin_sees_only_the_menu_of_its_modules(browser, company):
    page = _page(browser, company["admin"])
    page.goto(f"/{CODE}/admin")
    pagina_klaar(page)
    menu = {label for label in page.evaluate(_MENU) if "Werkruimte" not in label}
    page.close()
    on = {"Werkbank", "Formulieren", "Pagina's", "Media"}
    off = {
        "Activiteiten",
        "Leden",
        "Betalingen",
        "Vergaderingen",
        "Nieuwsbrief",
        "Design Studio",
        "Rapporten",
        "Raakje",
        "AI · Raakje",
    }
    assert on <= menu, menu
    assert not off & menu, off & menu
    assert {"Gebruikers", "Wijzigingen", "E-maillog", "Info"} <= menu, menu


def test_4_the_dashboard_shows_open_tasks_only(browser, company):
    page = _page(browser, company["admin"])
    page.goto(f"/{CODE}/admin")
    pagina_klaar(page)
    lines = [s.strip() for s in page.locator("main").inner_text().split("\n")]
    page.close()
    tiles = [
        s
        for s in lines
        if s
        and not re.match(r"^[€\d\s.,%—-]+$", s)
        and s not in ("Rapport", "Dashboard")
        and not s.startswith("Cijfers van")
    ]
    assert tiles == ["Open taken (werkbank)"], tiles


def test_5_a_visitor_sees_the_seeded_site(browser, company):
    page = _page(browser)
    page.goto(f"/{CODE}/")
    pagina_klaar(page)
    main = page.locator("main").inner_text()
    footer = page.locator("footer").inner_text()
    nav = {
        t.strip()
        for t in page.eval_on_selector_all(
            "#site-nav-breed a", "els => els.map(e => e.textContent)"
        )
        if t.strip()
    }
    account = page.locator("[data-site-account]").inner_text().strip()
    page.close()
    assert f"Welkom bij {NAME}" in main, "the seeded home text"
    assert NAME in footer, "the tenant's name in the legal line"
    assert "Word lid" not in main, "no membership band"
    assert "Inschrijven" not in main and "Activiteiten" not in main, "no activity cards"
    # Home, plus the page the tenant itself published (step 8's); the way to
    # sign in stands in the account's place and reads "Inloggen" (#1588).
    assert nav == {"Home", "Vragen"}, nav
    assert account == "Inloggen", account


@pytest.mark.parametrize("path", ["activiteiten", "lid-worden", "fotos"])
def test_6_the_pages_of_modules_that_are_off_are_not_found(browser, company, path):
    page = _page(browser)
    answer = page.goto(f"/{CODE}/{path}")
    text = page.locator("body").inner_text().lower()
    page.close()
    assert answer.status == 404, (path, answer.status)
    assert "niet gevonden" in text


def test_7_the_sitemap_holds_nothing_of_a_module_that_is_off(browser, company):
    page = _page(browser)
    answer = page.request.get(f"/{CODE}/sitemap.xml")
    body = answer.body()
    page.close()
    assert answer.ok
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    paths = [
        re.sub(r"^https?://[^/]+", "", loc.text or "")
        for loc in ElementTree.fromstring(body).findall("s:url/s:loc", ns)
    ]
    assert paths, "an empty sitemap"
    for off in ("/activiteiten", "/lid-worden", "/fotos", "/archief"):
        assert not [p for p in paths if p.endswith(off) or f"{off}/" in p], (off, paths)
    assert any(p.rstrip("/").endswith("/vragen") for p in paths), paths


def test_8_a_form_on_a_page_lands_under_formulieren(browser, company):
    # The visitor on the platform host, where a tenant is reached by its prefix
    # (as on PROD): the form's post must keep that prefix (#1477).
    page = _page(browser, base=PLATFORM)
    page.goto(f"/{CODE}/vragen")
    pagina_klaar(page)
    page.get_by_role("link", name="Stel je vraag").click()
    pagina_klaar(page)
    # At a person's pace: the form guard drops, with the ordinary thanks, what
    # comes in within two seconds of the page (#1297).
    for selector, text in (
        ("#submitter_name", "Een bezoeker"),
        ("#submitter_email", "bezoeker@example.org"),
        (f'[name="{company["field"]}"]', "Een volkoren"),
    ):
        page.locator(selector).press_sequentially(text, delay=100)
    # The post must carry the prefix itself (#889: the URL says where you are,
    # the `raak_tenant` cookie is only the safety net). Without the cookie, a
    # bare `/formulier/…` reached the platform tenant: "Formulier niet gevonden".
    page.context.clear_cookies()
    # Wait for the answer of the post itself (#1812). The page reached
    # `networkidle` long before the click — the typing above takes seconds — so
    # waiting for that state returned at once, and the page was closed while the
    # post was still on its way: on a busy runner the submission was never sent.
    with page.expect_response(
        lambda answer: answer.request.method == "POST" and "/formulier/" in answer.url
    ) as answered:
        page.get_by_role("button", name="Verzenden").first.click()
    assert answered.value.status == 200, answered.value.status
    assert f"/{CODE}/formulier/" in answered.value.url, "the post lost the tenant's prefix"
    page.close()

    page = _page(browser, company["admin"])
    page.goto(f"/{CODE}/admin/formulieren/{company['form_id']}/inzendingen")
    pagina_klaar(page)
    text = page.locator("main").inner_text()
    page.close()
    assert "Een bezoeker" in text, "the submission under Formulieren"
