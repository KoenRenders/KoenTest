"""CR-19 #1477 — the screens follow the module set (C6 tests 6, 7; part of the
public shell, the dashboard, the reporting folders, the newsletter audiences
and the tenant editor), and a page can be the home page.

**The association first, against a snapshot taken on the old code** (CLAUDE.md:
a conversion that touches screens is measured against the output before it).
Taken on 2 October 2026 on this branch before any screen changed: the home
page's fee band, "Word lid" and activity cards; the sitemap's paths; the six
dashboard tiles; the footer heading "Met steun van". A tenant with every
module on must still render exactly those.

Proven red by breaking each screen on purpose, one at a time: the home page's
flags forced on, the sitemap over every module, every dashboard tile, every
reporting folder, every newsletter audience, the editor saving every key, no
"Partners" for a company — each made exactly its own test fail. Against master
the module does not import (no `TenantKind`, no module registry).
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.cms.api import CmsPage
from app.domains.mdm import tenant_lookup
from app.domains.mdm.api import Organization, TenantKind
from app.kernel.modules import ModuleCode
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from app.kernel.tenant_config import get_setting, set_setting
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

EVERY = frozenset(code.value for code in ModuleCode)
COMPANY = frozenset({"cms", "media", "forms", "workflow"})
TILES = (
    "Gezinnen",
    "Actieve gezinnen",
    "Personen (actief lid)",
    "Komende activiteiten",
    "Open taken (werkbank)",
    "Openstaand saldo",
)
# The association's sitemap on the old code, as paths (order is not meaning).
# Without `/home-intro` and `/site-footer` since #1510: they are site blocks,
# not pages; every other path of the old sitemap stays.
SITEMAP_BEFORE = {
    "/",
    "/activiteiten",
    "/activiteiten/archief",
    "/fotos",
    "/lid-worden",
    "/berichten",
    "/privacy",
}


@pytest.fixture
def modules(monkeypatch):
    """Set the default tenant's module set as the middleware will read it."""

    def apply(codes: frozenset[str]):
        monkeypatch.setattr(tenant_lookup, "_modules_cache", {TENANT_MILLEGEM_ID: codes})

    apply(EVERY)
    yield apply
    tenant_lookup.invalidate_tenant_codes()


def _admin(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _sitemap(client) -> set[str]:
    xml = client.get("/sitemap.xml").text
    return {
        re.sub(r"^https?://[^/]+(/raakmillegem)?", "", u) or "/"
        for u in re.findall(r"<loc>([^<]*)</loc>", xml)
    }


def _tiles(html: str) -> set[str]:
    return {t for t in TILES if t in html}


# ── The association: unchanged ──────────────────────────────────────────────


def test_an_association_renders_as_before(client, db_session, modules):
    home = client.get("/").text
    assert 'lid-worden"' in home and "per gezin" in home and "Activiteiten</h2>" in home
    assert "Contacteer ons" in home and 'id="nb-home-link"' in home
    assert _sitemap(client) == SITEMAP_BEFORE
    _admin(client)
    assert _tiles(client.get("/admin").text) == set(TILES)
    panel = client.get("/admin/rapporten/nieuw").text
    assert set(re.findall(r'name="toggle_class" value="([^"]+)"', panel)) == {
        "Leden",
        "Activiteiten",
        "Betalingen",
        "Formulieren",
        "Taken",
    }

    from app.ui import site_context

    assert site_context(db_session)["sponsors_kop"] == "Met steun van"


# ── A company: what is off is absent ────────────────────────────────────────


def test_a_company_home_page_has_no_fee_no_cards_and_no_newsletter(client, modules):
    modules(COMPANY)
    home = client.get("/").text
    assert 'lid-worden"' not in home and "per gezin" not in home
    assert "Activiteiten</h2>" not in home
    assert "Contacteer ons" in home, "forms is on"
    assert 'id="nb-home-link"' not in home, "the newsletter module is off"


def test_the_chat_bubble_needs_the_chatbot_module(db_session, monkeypatch, modules):
    from app.config import settings
    from app.ui import site_context

    monkeypatch.setattr(settings, "chat_enabled", True)
    from app.kernel.modules import current_modules

    for codes, expected in ((EVERY, True), (COMPANY, False)):
        token = current_modules.set(codes)
        try:
            assert site_context(db_session)["chat_enabled"] is expected
        finally:
            current_modules.reset(token)


def test_the_sitemap_lists_only_the_paths_of_modules_that_are_on(client, modules):
    modules(COMPANY)
    paths = _sitemap(client)
    # /fotos is Media's route but the albums of activities: it needs both, as
    # its menu item does (C6 test 13 found it in the sitemap of a company).
    assert {"/activiteiten", "/activiteiten/archief", "/lid-worden", "/fotos"}.isdisjoint(paths)
    assert {"/", "/berichten"} <= paths


def test_the_photo_albums_need_activities_as_well_as_media(client, modules):
    """The public album routes are served by Media and guarded for Activiteiten
    too (`require_module(MEDIA, also=(ACTIVITIES,))`, #1477): a company, with
    Media on and Activiteiten off, finds no /fotos; an association does."""
    modules(COMPANY)
    assert client.get("/fotos").status_code == 404
    modules(EVERY)
    assert client.get("/fotos").status_code == 200
    assert "/fotos" in _sitemap(client)


def test_the_dashboard_shows_only_the_tiles_of_modules_that_are_on(client, modules):
    modules(COMPANY)
    _admin(client)
    assert _tiles(client.get("/admin").text) == {"Open taken (werkbank)"}


def test_the_reporting_panel_offers_only_the_folders_of_modules_that_are_on(client, modules):
    modules(COMPANY | {"reporting"})
    _admin(client)
    panel = client.get("/admin/rapporten/nieuw").text
    folders = set(re.findall(r'name="toggle_class" value="([^"]+)"', panel))
    assert folders == {"Formulieren", "Taken"}, folders


def test_without_membership_the_newsletter_offers_only_iedereen(client, db_session, modules):
    from app.domains.newsletter.service import create_newsletter

    letter = create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    db_session.commit()
    _admin(client)
    modules(EVERY)
    assert (
        len(re.findall(r'name="audience"', client.get(f"/admin/nieuwsbrieven/{letter.id}").text))
        == 3
    )
    modules(EVERY - {"membership"})
    page = client.get(f"/admin/nieuwsbrieven/{letter.id}").text
    assert re.findall(r'name="audience" value="([^"]*)"', page) == ["both"]
    assert "Iedereen" in page


def test_a_company_footer_says_partners(db_session):
    from app.ui import site_context

    org = db_session.get(Organization, TENANT_MILLEGEM_ID)
    org.kind = TenantKind.COMPANY
    db_session.flush()
    assert site_context(db_session)["sponsors_kop"] == "Partners"


# ── The tenant editor: settings of a module that is off ─────────────────────


def test_the_editor_hides_the_settings_of_modules_that_are_off_and_keeps_them(
    client, platform_workspace, db_session
):
    from app.domains.auth.api import csrf_token_for
    from app.domains.auth.models import User, UserRole
    from app.domains.mdm.api import create_tenant

    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not db_session.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
    company = create_tenant(db_session, name="Firma", code="firma-1477", kind=TenantKind.COMPANY)
    association = create_tenant(db_session, name="Club", code="club-1477")
    set_setting(db_session, "membership_price_full", "40.00", tenant_id=company.id)
    db_session.commit()
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)

    company_page = client.get(f"/admin/tenants/{company.id}").text
    # #1498: a module that is off keeps its card; its settings are folded away
    # in it (still on the form, so a save keeps them), not left out.
    for card, key in (
        ("membership", "membership_price_full"),
        ("activities", "max_item_quantity"),
        ("payment", "payment_term_days"),
        ("payment", "mollie_api_key"),
        ("chatbot", "admin_chat_enabled"),
    ):
        body = re.search(rf'data-card="{card}".*?</section>', company_page, re.S).group(0)
        assert f'name="{key}"' in body and 'x-show="on" style="display: none"' in body, key
    assert 'name="tagline"' in company_page
    association_page = client.get(f"/admin/tenants/{association.id}").text
    assert 'name="membership_price_full"' in association_page

    saved = client.post(
        f"/admin/tenants/{company.id}",
        data={"tagline": "Brood en banket"},
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    assert saved.status_code == 200
    assert get_setting(db_session, "membership_price_full", tenant_id=company.id) == "40.00", (
        "a hidden setting survives a save — switching a module off deletes nothing"
    )


# ── A page as the home page ─────────────────────────────────────────────────


def test_a_flagged_page_is_the_home_page_and_the_flag_moves(client, db_session):
    from app.domains.cms.api import update_page
    from app.schemas.cms import CmsPageUpdate

    first = CmsPage(
        title="Over ons",
        slug="over-ons-1477",
        content="<p>Wij bakken brood.</p>",
        is_published=True,
    )
    second = CmsPage(
        title="Aanbod",
        slug="aanbod-1477",
        content="<p>Taarten op bestelling.</p>",
        is_published=True,
    )
    db_session.add_all([first, second])
    db_session.commit()

    assert "Wij bakken brood." not in client.get("/").text
    update_page(db_session, first.id, CmsPageUpdate(is_home=True))
    assert "Wij bakken brood." in client.get("/").text

    update_page(db_session, second.id, CmsPageUpdate(is_home=True))
    db_session.refresh(first)
    assert not first.is_home, "one home page per tenant: the flag moved"
    assert "Taarten op bestelling." in client.get("/").text

    update_page(db_session, second.id, CmsPageUpdate(is_home=False))
    assert "per gezin" in client.get("/").text, "no flag: the composition again"
