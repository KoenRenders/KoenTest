"""CR-19 #1478 — the tenant kind, creating a tenant that seeds, `set_modules`
with its dependencies, the editor with the module set, and the landing without
membership (C6 tests 2, 3, 9).

Proven red against master `c644eba1`: there is no `TenantKind`, no
`set_modules`, no `seed_site_blocks` and no `record_counts`, so the module does
not import. The three gate-like rules are also broken on this branch on purpose
— see `test_a_dependency_is_refused_before_anything_changes` and the editor test.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text as sql

from app.domains.activities.api import Activity
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, landing_for, make_session_value
from app.domains.auth.models import User, UserRole
from app.domains.cms.api import CmsPage
from app.domains.mdm import tenant_lookup
from app.domains.mdm.api import (
    Tenant,
    TenantFout,
    TenantKind,
    enabled_modules,
    set_modules,
)
from app.kernel.modules import ModuleCode, current_modules, record_counts
from app.kernel.tenancy import ACCOUNT_RAAK_ID, TENANT_MILLEGEM_ID
from tests._sites import new_site
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

# CR-21 (Q49): the shop is off by default, so an association's "full" set is
# every module but the shop.
EVERY = {code.value for code in ModuleCode if code not in (ModuleCode.SHOP, ModuleCode.INVOICES)}
COMPANY = {"cms", "media", "forms"}


def _operator(client, db_session) -> str:
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not db_session.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db_session.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _ticked(html: str) -> set[str]:
    """The module checkboxes that are ticked, read from the rendered form."""
    import re

    # #1933: the module's switch in its card's head (it was a checkbox).
    tags = re.findall(r'<input type="checkbox" role="switch" name="modules"[^>]*>', html)
    assert len(tags) == len(ModuleCode), f"{len(tags)} module checkboxes"
    return {re.search(r'value="(\w+)"', t).group(1) for t in tags if "checked" in t}


def _blocks(db_session, tenant_id: int) -> dict[str, CmsPage]:
    pages = (
        db_session.query(CmsPage)
        .filter(CmsPage.tenant_id == tenant_id)
        .execution_options(include_all_tenants=True)
        .all()
    )
    return {p.slug: p for p in pages}


# ── C6 test 2: the kind gives the defaults, and the site is not empty ───────


@pytest.mark.parametrize(
    "kind,expected", [(TenantKind.COMPANY, COMPANY), (TenantKind.ASSOCIATION, EVERY), (None, EVERY)]
)
def test_a_new_tenant_starts_with_its_kinds_modules_a_footer_and_a_home_page(
    db_session, kind, expected
):
    org = new_site(db_session, name="Bakkerij & Co", code="bakkerij-1478", kind=kind)
    assert org.kind is (kind or TenantKind.ASSOCIATION)
    assert enabled_modules(org.id, db=db_session) == expected

    blocks = _blocks(db_session, org.id)
    # CR-32 R17: the footer block and the tenant's home page (flagged, in the CMS);
    # `home-intro` is no site block any more.
    assert set(blocks) == {"site-footer", "start"}
    assert all(b.is_published and not b.show_in_nav for b in blocks.values())
    assert blocks["start"].is_home and blocks["start"].title == "Bakkerij & Co"
    from app.domains.cms.api import published_document, render_document

    home = published_document(db_session, blocks["start"])
    assert "Welkom bij Bakkerij & Co." in str(home), "the welcome line is the page's intro"
    assert "Welkom bij Bakkerij &amp; Co." in render_document(home, db_session), "escaped, not raw"
    # The composition follows the modules the kind gives (CR-19): a band and
    # activities only where those modules are on.
    kinds_of_block = {b["type"] for b in home["content"]}
    assert ("activities" in kinds_of_block) is ("activities" in expected)
    assert blocks["site-footer"].content == "<p>Bakkerij &amp; Co</p>"


def test_an_unknown_kind_is_refused(db_session):
    with pytest.raises(TenantFout, match="vereniging of bedrijf"):
        new_site(db_session, name="X", code="x-1478", kind="KERK")
    assert not db_session.query(Tenant).filter(Tenant.code == "x-1478").first()


def test_every_existing_unit_is_an_association_and_nothing_else_has_a_kind(db_session):
    """Every department an association; the platform its own kind since #1523
    (migration 191). Since CR-20 the kind is the tenant's (`mdm.tenants.kind`,
    NOT NULL); an organisation has none."""
    rows = db_session.execute(sql("SELECT code, kind FROM mdm.tenants")).all()
    assert {r.kind for r in rows} >= {"VERENIGING", "PLATFORM"}
    for code, kind in rows:
        expected = "PLATFORM" if code == "platform" else "VERENIGING"
        assert kind == expected, (code, kind)


# ── C6 test 3: dependencies ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "codes,message",
    [
        ({"cms", "designstudio"}, "Design Studio heeft Activiteiten nodig."),
        ({"cms", "payment"}, "Betalingen heeft Activiteiten, Leden of Webshop nodig."),
        ({"cms", "stamboom"}, "Onbekende module."),
    ],
)
def test_a_dependency_is_refused_before_anything_changes(db_session, codes, message):
    org = new_site(db_session, name="Proef", code="proef-1478", kind=TenantKind.COMPANY)
    with pytest.raises(TenantFout) as refused:
        set_modules(db_session, org.id, codes)
    assert str(refused.value) == message
    assert enabled_modules(org.id, db=db_session) == COMPANY, "nothing changed"


@pytest.mark.parametrize(
    "alternatives,message",
    [
        ((ModuleCode.ACTIVITIES,), "Betalingen heeft Activiteiten nodig."),
        (
            (ModuleCode.ACTIVITIES, ModuleCode.MEMBERSHIP),
            "Betalingen heeft Activiteiten of Leden nodig.",
        ),
        (
            (ModuleCode.ACTIVITIES, ModuleCode.MEMBERSHIP, ModuleCode.MEETINGS),
            "Betalingen heeft Activiteiten, Leden of Vergaderingen nodig.",
        ),
    ],
)
def test_the_alternatives_of_a_refused_module_read_as_a_dutch_list(
    db_session, monkeypatch, alternatives, message
):
    """#1888: one, two and three alternatives, on the sentence the operator reads.
    The registry gets the alternatives of the case (a copy, put back by monkeypatch):
    with a third alternative payments needs, the sentence must not read "of … of".

    Broken on purpose (14 October 2026, put back): `_dutch_enumeration` returning
    `" of ".join(labels)` -> the three-alternative case reads "Activiteiten of Leden
    of Vergaderingen"."""
    from dataclasses import replace

    from app.kernel import modules

    payment = replace(modules.REGISTRY[ModuleCode.PAYMENT], depends_on=(alternatives,))
    monkeypatch.setitem(modules.REGISTRY, ModuleCode.PAYMENT, payment)
    org = new_site(db_session, name="Proef", code="proef-1888", kind=TenantKind.COMPANY)
    with pytest.raises(TenantFout) as refused:
        set_modules(db_session, org.id, {"cms", "payment"})
    assert str(refused.value) == message


def test_a_valid_set_is_saved_and_the_cache_cleared(db_session, monkeypatch):
    org = new_site(db_session, name="Proef", code="proef2-1478", kind=TenantKind.COMPANY)
    monkeypatch.setattr(tenant_lookup, "_modules_cache", {org.id: frozenset({"cms"})})

    set_modules(db_session, org.id, {"cms", "activities", "designstudio", "payment"})
    assert enabled_modules(org.id, db=db_session) == {
        "cms",
        "activities",
        "designstudio",
        "payment",
    }
    assert tenant_lookup._modules_cache is None, "the next request must read the new set"


# ── The editor: counts, the set, the refusal ────────────────────────────────


def test_record_counts_count_this_tenants_live_records(db_session):
    from app.soft_delete import soft_delete

    org = new_site(db_session, name="Telproef", code="tel-1478", kind=TenantKind.ASSOCIATION)
    live = Activity(name="Telt", tenant_id=org.id)
    gone = Activity(name="Telt niet", tenant_id=org.id)
    db_session.add_all([live, gone])
    db_session.flush()
    soft_delete(gone)
    db_session.flush()

    counts = record_counts(db_session, org.id)
    assert counts[ModuleCode.ACTIVITIES] == 1
    assert counts[ModuleCode.CMS] == 2, "the two seeded site blocks"
    uncounted = {ModuleCode.REPORTING, ModuleCode.INVOICES}
    assert set(counts) == set(ModuleCode) - uncounted, "reporting and invoices are uncounted"


def test_the_editor_shows_the_kind_and_the_modules_and_refuses_a_missing_dependency(
    client, platform_workspace, db_session
):
    csrf = _operator(client, db_session)
    org = new_site(db_session, name="Editorproef", code="ed-1478", kind=TenantKind.COMPANY)

    page = client.get(f"/admin/tenants/{org.id}?bewerken=1").text
    # #1533: the kind is a choice now, BEDRIJF ticked.
    assert re.search(r'<option value="BEDRIJF" selected', page)
    assert _ticked(page) == COMPANY
    # #1933 (Koen, 13 October 2026): no count of records in a module's head.
    assert "gegevens" not in re.search(r'data-card="cms".*?</section>', page, re.S).group(0)

    # #1498: one Opslaan for modules and settings; the refusal on the card concerned.
    refused = client.post(
        f"/admin/tenants/{org.id}",
        data={"modules_shown": "1", "modules": ["cms", "designstudio"]},
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    assert refused.status_code == 422
    assert "Design Studio heeft Activiteiten nodig." in refused.text
    assert enabled_modules(org.id, db=db_session) == COMPANY

    saved = client.post(
        f"/admin/tenants/{org.id}",
        data={"modules_shown": "1", "modules": ["cms", "media", "forms", "newsletter"]},
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    assert saved.status_code == 200
    assert enabled_modules(org.id, db=db_session) == COMPANY | {"newsletter"}


def test_the_new_tenant_page_is_operator_only_and_offers_the_kind(
    client, platform_workspace, db_session
):
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    db_session.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").delete()
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    assert client.get("/admin/tenants/nieuw", follow_redirects=False).status_code == 403

    csrf = _operator(client, db_session)
    page = client.get("/admin/tenants/nieuw").text
    assert 'name="kind" value="VERENIGING"' in page and 'name="kind" value="BEDRIJF"' in page

    client.post(
        "/admin/tenants",
        data={
            "site_name": "Garage Peeters",
            "code": "garage-1478",
            "kind": "BEDRIJF",
            "account_id": str(ACCOUNT_RAAK_ID),
        },
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    org = db_session.query(Tenant).filter(Tenant.code == "garage-1478").one()
    assert org.kind is TenantKind.COMPANY
    assert enabled_modules(org.id, db=db_session) == COMPANY
    assert "Bedrijf" in client.get("/admin/tenants").text


# ── C6 test 9: landing without membership ───────────────────────────────────


def test_a_user_without_an_admin_role_lands_on_the_account_page_with_or_without_membership(
    db_session,
):
    """Rewritten with CR-22 (#1707; Koen, 7 October 2026). This test pinned "/"
    for a tenant without the membership module, because Mijn gezin — the
    landing then — answers 404 there. The landing is the account page now, and
    that page exists on every tenant: with or without members, whoever signs
    in as a person lands on "Mijn <tenant>".

    What it still guards, as test 9 did: the landing never points at a page
    this tenant does not serve. A session that signs in as no person has no
    account page either, and lands on the site.
    """
    from tests.conftest import create_test_family

    create_test_family(db_session, email="iemand-1478@example.com")
    db_session.commit()
    for modules in (EVERY - {"membership"}, EVERY):
        token = current_modules.set(frozenset(modules))
        try:
            assert landing_for(db_session, "iemand-1478@example.com") == "/mijn"
            assert landing_for(db_session, "niemand-1478@example.com") == "/"
        finally:
            current_modules.reset(token)
    assert TENANT_MILLEGEM_ID  # the default tenant keeps every module
