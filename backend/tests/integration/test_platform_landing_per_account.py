"""#1525 (CR-19) — the platform landing lists the tenants per account, and its
text is the platform's own home-intro, which the operator edits in Pagina's.

Red against master: the landing had one list "Afdelingen" with every active
unit and no account headings, and its text stood in the template, so editing a
page changed nothing on it.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.cms.api import CmsPage
from app.domains.mdm.api import (
    Organization,
    OrganizationType,
    TenantKind,
    create_account,
    create_tenant,
)

pytestmark = pytest.mark.ui_serverrendered

PLATFORM_HOST = "platform.example.test"


@pytest.fixture
def platform_host(monkeypatch):
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "platform_hosts", PLATFORM_HOST)
    invalidate_tenant_codes()
    yield PLATFORM_HOST
    invalidate_tenant_codes()


def _landing(client) -> str:
    response = client.get("/", headers={"host": PLATFORM_HOST})
    assert response.status_code == 200
    assert "Aanmelden als platformbeheerder" in response.text, "this is the landing"
    return response.text


def _groups(html: str) -> dict[str, list[str]]:
    """Each account heading on the landing, with the tenant names under it."""
    main = html.split("Aanmelden als platformbeheerder")[0]
    parts = re.split(r"<h2[^>]*>\s*(.*?)\s*</h2>", main, flags=re.S)
    return {
        parts[i]: re.findall(r'<span class="font-semibold text-ink">(.*?)</span>', parts[i + 1])
        for i in range(1, len(parts), 2)
        if 'class="font-semibold text-ink"' in parts[i + 1]
    }


def _platform(db) -> Organization:
    return (
        db.query(Organization)
        .filter(Organization.org_type == OrganizationType.PLATFORM)
        .execution_options(include_all_tenants=True)
        .one()
    )


def _intro(db) -> CmsPage:
    return (
        db.query(CmsPage)
        .filter(CmsPage.tenant_id == _platform(db).id, CmsPage.slug == "home-intro")
        .execution_options(include_all_tenants=True)
        .one()
    )


def test_the_tenants_stand_under_their_account_and_an_inactive_one_is_absent(
    client, db_session, platform_host
):
    bakers = create_account(db_session, name="Bakkersgilde", code="bakkersgilde-1525")
    create_tenant(
        db_session,
        name="Bakkerij Peeters",
        code="peeters-1525",
        parent_id=bakers.id,
        kind=TenantKind.COMPANY,
    )
    closed = create_tenant(
        db_session, name="Bakkerij Gesloten", code="gesloten-1525", parent_id=bakers.id
    )
    closed.is_active = False
    create_tenant(db_session, name="Losse Club", code="los-1525")
    create_account(db_session, name="Leeg Account", code="leeg-1525")
    db_session.commit()

    groups = _groups(_landing(client))
    print("MEASURE", groups)
    assert groups["Bakkersgilde"] == ["Bakkerij Peeters"], "the inactive tenant is absent"
    raak = [name for name, tenants in groups.items() if "Raak Millegem" in tenants]
    assert len(raak) == 1 and raak[0] != "Bakkersgilde", "the seeded units under their own account"
    assert "Bakkerij Peeters" not in groups[raak[0]]
    assert groups["Overige"] == ["Losse Club"], "a tenant without an account does not vanish"
    assert list(groups)[-1] == "Overige"
    assert "Leeg Account" not in groups, "an account without an active tenant is left out"
    assert "Bakkerij Gesloten" not in str(groups)


def test_the_seeded_text_is_neutral_and_stands_above_the_list(client, db_session, platform_host):
    intro = _intro(db_session)
    assert intro.is_published and not intro.show_in_nav
    html = _landing(client)
    assert "Eén platform voor verenigingen en organisaties" in html
    assert "Raak-afdelingen" not in html
    assert html.index("Ook op het platform?") < html.index("Raak Millegem"), "text above list"


def test_editing_the_platforms_page_in_paginas_changes_the_landing(
    client, db_session, platform_host
):
    user = User(email="operator-1525@example.com", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
    db_session.commit()
    session = make_session_value("operator-1525@example.com")
    client.cookies.set(SESSION_COOKIE, session)
    page_id = _intro(db_session).id

    saved = client.post(
        f"/admin/paginas/{page_id}",
        data={
            "title": "Home intro",
            "slug": "home-intro",
            "content": "<p>Welkom op ons platform, nu met eigen woorden.</p>",
            "is_published": "1",
        },
        headers={
            "host": PLATFORM_HOST,
            "X-CSRF-Token": csrf_token_for(session),
            "HX-Request": "true",
        },
    )
    assert saved.status_code == 200
    html = _landing(client)
    assert "Welkom op ons platform, nu met eigen woorden." in html
    assert "Eén platform voor verenigingen" not in html


def test_with_pages_off_the_landing_shows_the_list_only(
    client, db_session, platform_host, monkeypatch
):
    from app.domains.mdm import tenant_lookup

    # The request reads the cached sets; the same seam as the other module tests.
    off = frozenset({"media", "forms", "workflow"})
    monkeypatch.setattr(tenant_lookup, "_modules_cache", {_platform(db_session).id: off})
    html = _landing(client)
    assert "Eén platform voor verenigingen" not in html
    assert "Raak Millegem" in html
