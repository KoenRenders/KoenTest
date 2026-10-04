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
    Organization,
    TenantFout,
    TenantKind,
    create_tenant,
    enabled_modules,
    set_modules,
)
from app.kernel.modules import ModuleCode, current_modules, record_counts
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

EVERY = {code.value for code in ModuleCode}
COMPANY = {"cms", "media", "forms", "workflow"}


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

    tags = re.findall(r'<input type="checkbox" name="modules"[^>]*>', html)
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
def test_a_new_tenant_starts_with_its_kinds_modules_and_two_site_blocks(db_session, kind, expected):
    org = create_tenant(db_session, name="Bakkerij & Co", code="bakkerij-1478", kind=kind)
    assert org.kind is (kind or TenantKind.ASSOCIATION)
    assert enabled_modules(org.id, db=db_session) == expected

    blocks = _blocks(db_session, org.id)
    assert set(blocks) == {"home-intro", "site-footer"}
    assert all(b.is_published and not b.show_in_nav for b in blocks.values())
    assert "Welkom bij Bakkerij &amp; Co." in blocks["home-intro"].content, "escaped, not raw"
    assert blocks["site-footer"].content == "<p>Bakkerij &amp; Co</p>"


def test_an_unknown_kind_is_refused(db_session):
    with pytest.raises(TenantFout, match="vereniging of bedrijf"):
        create_tenant(db_session, name="X", code="x-1478", kind="KERK")
    assert not db_session.query(Organization).filter(Organization.code == "x-1478").first()


def test_every_existing_unit_is_an_association_and_nothing_else_has_a_kind(db_session):
    """Every UNIT an association; the PLATFORM its own kind since #1523
    (migration 191); an ACCOUNT none."""
    rows = db_session.execute(sql("SELECT org_type, kind FROM mdm.organizations")).all()
    assert {r.org_type for r in rows} >= {"UNIT", "ACCOUNT", "PLATFORM"}
    expected = {"UNIT": "VERENIGING", "PLATFORM": "PLATFORM"}
    for org_type, kind in rows:
        assert kind == expected.get(org_type), (org_type, kind)


# ── C6 test 3: dependencies ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "codes,message",
    [
        ({"cms", "designstudio"}, "Design Studio heeft Activiteiten nodig."),
        ({"cms", "payment"}, "Betalingen heeft Activiteiten of Leden nodig."),
        ({"cms", "stamboom"}, "Onbekende module."),
    ],
)
def test_a_dependency_is_refused_before_anything_changes(db_session, codes, message):
    org = create_tenant(db_session, name="Proef", code="proef-1478", kind=TenantKind.COMPANY)
    with pytest.raises(TenantFout) as refused:
        set_modules(db_session, org.id, codes)
    assert str(refused.value) == message
    assert enabled_modules(org.id, db=db_session) == COMPANY, "nothing changed"


def test_a_valid_set_is_saved_and_the_cache_cleared(db_session, monkeypatch):
    org = create_tenant(db_session, name="Proef", code="proef2-1478", kind=TenantKind.COMPANY)
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

    org = create_tenant(db_session, name="Telproef", code="tel-1478", kind=TenantKind.ASSOCIATION)
    live = Activity(name="Telt", tenant_id=org.id)
    gone = Activity(name="Telt niet", tenant_id=org.id)
    db_session.add_all([live, gone])
    db_session.flush()
    soft_delete(gone)
    db_session.flush()

    counts = record_counts(db_session, org.id)
    assert counts[ModuleCode.ACTIVITIES] == 1
    assert counts[ModuleCode.CMS] == 2, "the two seeded site blocks"
    assert set(counts) == set(ModuleCode) - {ModuleCode.REPORTING}, "reporting is uncounted"


def test_the_editor_shows_the_kind_and_the_modules_and_refuses_a_missing_dependency(
    client, db_session
):
    csrf = _operator(client, db_session)
    org = create_tenant(db_session, name="Editorproef", code="ed-1478", kind=TenantKind.COMPANY)

    page = client.get(f"/admin/tenants/{org.id}").text
    # #1533: the kind is a choice now, BEDRIJF ticked.
    assert re.search(r'name="kind" value="BEDRIJF"[^>]*checked', page)
    assert _ticked(page) == COMPANY
    # #1498: the count stands in each module's card header.
    assert re.search(r'data-card="cms".*?2 gegevens', page, re.S), "the two seeded site blocks"
    assert re.search(r'data-card="activities".*?0 gegevens', page, re.S)

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
        data={"modules_shown": "1", "modules": ["cms", "media", "forms", "workflow", "newsletter"]},
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    assert saved.status_code == 200
    assert enabled_modules(org.id, db=db_session) == COMPANY | {"newsletter"}


def test_the_new_tenant_page_is_operator_only_and_offers_the_kind(client, db_session):
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
        data={"name": "Garage Peeters", "code": "garage-1478", "kind": "BEDRIJF"},
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    org = db_session.query(Organization).filter(Organization.code == "garage-1478").one()
    assert org.kind is TenantKind.COMPANY
    assert enabled_modules(org.id, db=db_session) == COMPANY
    assert "Bedrijf" in client.get("/admin/tenants").text


# ── C6 test 9: landing without membership ───────────────────────────────────


def test_a_user_without_an_admin_role_lands_on_the_site_without_membership(db_session):
    token = current_modules.set(frozenset(EVERY - {"membership"}))
    try:
        assert landing_for(db_session, "iemand-1478@example.com") == "/"
    finally:
        current_modules.reset(token)
    token = current_modules.set(frozenset(EVERY))
    try:
        assert landing_for(db_session, "iemand-1478@example.com") == "/leden/gezin"
    finally:
        current_modules.reset(token)
    assert TENANT_MILLEGEM_ID  # the default tenant keeps every module
