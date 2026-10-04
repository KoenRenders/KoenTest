"""#1523 — the platform is a tenant kind, with a company's module set for now.

Measured on HDEV before: the PLATFORM organisation had no kind and all twelve
modules on (#1475 seeded it full), so its back-office menu showed Activiteiten,
Leden, Vergaderingen and the rest. Migration 191 gives it the kind PLATFORM and
the set of `DEFAULTS["PLATFORM"]`: pages, media, forms and the workbench. The
shell's screens belong to no module and stay.

Red against master: the platform's kind was NULL, its set all twelve, its menu
held Activiteiten, and the registry had no PLATFORM entry.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.mdm.api import (
    Organization,
    OrganizationType,
    TenantFout,
    TenantKind,
    create_tenant,
    enabled_modules,
)
from app.kernel.modules import DEFAULTS, ModuleCode

pytestmark = pytest.mark.ui_serverrendered

PLATFORM_HOST = "platform.example.test"
SHELL = (
    "/admin/tenants",
    "/admin/organisaties",
    "/admin/gebruikers",
    "/admin/ledenwijzigingen",
    "/admin/info",
)
ON = ("/admin/paginas", "/admin/media", "/admin/formulieren", "/admin/werkbank")
OFF = ("/admin/activiteiten", "/admin/leden", "/admin/vergaderingen", "/admin/nieuwsbrieven")


@pytest.fixture
def platform_host(monkeypatch):
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "platform_hosts", PLATFORM_HOST)
    invalidate_tenant_codes()
    yield PLATFORM_HOST
    invalidate_tenant_codes()


def _platform(db) -> Organization:
    return (
        db.query(Organization)
        .filter(Organization.org_type == OrganizationType.PLATFORM)
        .execution_options(include_all_tenants=True)
        .one()
    )


def _operator(client, db) -> None:
    user = User(email="operator-1523@example.com", is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
    db.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value("operator-1523@example.com"))


def test_the_platform_has_its_kind_and_its_set(db_session):
    platform = _platform(db_session)

    assert platform.kind is TenantKind.PLATFORM
    assert enabled_modules(platform.id, db=db_session) == {"cms", "media", "forms", "workflow"}


def test_the_platform_menu_is_the_shell_and_its_four_modules(client, db_session, platform_host):
    _operator(client, db_session)
    html = client.get("/admin/gebruikers", headers={"host": platform_host}).text
    nav = re.search(r'<nav id="admin-nav-zijbalk".*?</nav>', html, re.S)
    assert nav, "no admin menu on the platform"
    links = set(re.findall(r'href="([^"]+)"', nav.group(0)))

    for href in SHELL + ON:
        assert href in links, f"{href} is missing from the platform's menu"
    for href in OFF:
        assert href not in links, f"{href} belongs to a module the platform has off"


def test_the_registry_has_the_platforms_own_entry():
    """Equal to a company's today, but its own entry: the two will grow apart."""
    assert "PLATFORM" in DEFAULTS
    assert DEFAULTS["PLATFORM"] == DEFAULTS["BEDRIJF"]
    assert DEFAULTS["PLATFORM"] == {
        ModuleCode.CMS,
        ModuleCode.MEDIA,
        ModuleCode.FORMS,
        ModuleCode.WORKFLOW,
    }


def test_a_new_tenant_is_never_a_platform(client, db_session, platform_host):
    with pytest.raises(TenantFout):
        create_tenant(db_session, name="Tweede platform", code="tweede-platform", kind="PLATFORM")

    _operator(client, db_session)
    form = client.get("/admin/tenants/nieuw").text
    assert 'value="BEDRIJF"' in form and 'value="VERENIGING"' in form, "the form offers the kinds"
    assert 'value="PLATFORM"' not in form, "a new tenant can be made a platform"


def test_the_tenant_editor_shows_the_platforms_kind(client, db_session):
    _operator(client, db_session)
    html = client.get(f"/admin/tenants/{_platform(db_session).id}").text

    assert "Type: Platform" in re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))
