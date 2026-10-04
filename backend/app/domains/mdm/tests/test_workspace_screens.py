"""#1535 (CR-19) — platform administration in the platform workspace only; each
tenant workspace has its own "Onze organisatie" and "Instellingen".

- An ADMIN of tenant A reads and saves A's organisation and settings, the Mollie
  key included (stored, never shown back); the module switch is refused; B's
  screens are out of reach by URL and by POST.
- In a tenant workspace an operator's menu has the own screens and no Tenants or
  Organisaties, whose URLs answer 404 there; in the platform workspace the
  reverse.
- Wijzigingen and the e-mail log are unaffected.

Red against master: `/admin/instellingen` was a 301 to Tenants, there was no
`/admin/organisatie`, an ADMIN got 403 on every tenant screen, and Tenants and
Organisaties answered in every workspace.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.mdm.api import Organization, platform_tenant_id
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID
from app.kernel.tenant_config import get_setting

pytestmark = pytest.mark.ui_serverrendered

MOLLIE = "test_1535_dit_is_geen_echte_sleutel"


def _login(client, db, email: str, role: str, tenant_id: int | None) -> str:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code=role, tenant_id=tenant_id))
    db.commit()
    session = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, session)
    return csrf_token_for(session)


def _post(client, csrf: str, path: str, data: dict):
    return client.post(path, data=data, headers={"X-CSRF-Token": csrf, "HX-Request": "true"})


def _menu(html: str) -> set[str]:
    nav = html[html.index('id="admin-nav-zijbalk"') :]
    nav = nav[: nav.index("</nav>")]
    return set(re.findall(r'<a href="([^"]+)"', nav))


def test_an_admin_keeps_its_own_settings_and_the_mollie_key(client, db_session):
    csrf = _login(client, db_session, "admin-a-1535@example.com", "ADMIN", TENANT_MILLEGEM_ID)

    page = client.get("/admin/instellingen")
    assert page.status_code == 200
    assert 'name="mollie_api_key"' in page.text and 'type="password"' in page.text
    assert 'name="modules"' not in page.text and "modules_shown" not in page.text
    assert 'name="kind"' not in page.text and 'name="account_id"' not in page.text

    saved = _post(
        client,
        csrf,
        "/admin/instellingen",
        {"tagline": "Onze eigen ondertitel", "mollie_api_key": MOLLIE},
    )
    assert saved.status_code == 200
    assert (
        get_setting(db_session, "tagline", tenant_id=TENANT_MILLEGEM_ID) == "Onze eigen ondertitel"
    )
    assert get_setting(db_session, "mollie_api_key", tenant_id=TENANT_MILLEGEM_ID) == MOLLIE
    assert MOLLIE not in saved.text and MOLLIE not in client.get("/admin/instellingen").text, (
        "a secret is never shown back, only that it is set"
    )
    assert (
        get_setting(db_session, "tagline", tenant_id=TENANT_VOORBEELD_ID) != "Onze eigen ondertitel"
    )


def test_an_admin_keeps_its_own_organisation(client, db_session):
    csrf = _login(client, db_session, "admin-b-1535@example.com", "ADMIN", TENANT_MILLEGEM_ID)
    page = client.get("/admin/organisatie")
    assert page.status_code == 200
    assert 'hx-post="/admin/organisatie"' in page.text

    saved = _post(client, csrf, "/admin/organisatie", {"name": "Raak Millegem 1535"})
    assert saved.status_code == 200, saved.text[-400:]
    db_session.expire_all()
    assert db_session.get(Organization, TENANT_MILLEGEM_ID).name == "Raak Millegem 1535"
    assert db_session.get(Organization, TENANT_VOORBEELD_ID).name != "Raak Millegem 1535"


def test_an_admin_switches_no_module_and_reaches_no_other_tenant(client, db_session):
    csrf = _login(client, db_session, "admin-c-1535@example.com", "ADMIN", TENANT_MILLEGEM_ID)

    switch = _post(client, csrf, "/admin/instellingen", {"modules_shown": "1", "modules": ["cms"]})
    assert switch.status_code == 403
    assert _post(client, csrf, "/admin/instellingen", {"kind": "BEDRIJF"}).status_code == 403

    for path in (
        f"/admin/tenants/{TENANT_VOORBEELD_ID}",
        f"/admin/organisaties/{TENANT_VOORBEELD_ID}",
    ):
        assert client.get(path).status_code == 404, path
        assert _post(client, csrf, path, {"name": "Overgenomen"}).status_code == 404, path
    for path in (
        "/raakvoorbeeldafdeling/admin/instellingen",
        "/raakvoorbeeldafdeling/admin/organisatie",
    ):
        assert client.get(path, follow_redirects=False).status_code in (403, 404), path
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, make_session_value("admin-c-1535@example.com"))
        refused = _post(client, csrf, path, {"name": "Overgenomen", "tagline": "Overgenomen"})
        assert refused.status_code in (403, 404), path
    db_session.expire_all()
    assert db_session.get(Organization, TENANT_VOORBEELD_ID).name != "Overgenomen"
    assert get_setting(db_session, "tagline", tenant_id=TENANT_VOORBEELD_ID) != "Overgenomen"


def test_the_menu_and_the_platform_screens_follow_the_workspace(client, db_session):
    _login(client, db_session, "operator-1535@example.com", "OPERATOR", None)

    menu = _menu(client.get("/admin").text)
    assert {"/admin/organisatie", "/admin/instellingen"} <= menu
    assert not {"/admin/tenants", "/admin/organisaties"} & menu
    for path in (
        "/admin/tenants",
        "/admin/organisaties",
        "/admin/organisaties/nieuw",
        "/admin/gebruikers/alle-werkruimtes",
    ):
        assert client.get(path).status_code == 404, path
    assert "/admin/gebruikers/alle-werkruimtes" not in client.get("/admin/gebruikers").text


def test_on_the_platform_the_operator_has_the_platform_screens(platform_workspace, db_session):
    client = platform_workspace
    _login(client, db_session, "operator2-1535@example.com", "OPERATOR", None)

    menu = _menu(client.get("/admin").text)
    assert {"/admin/tenants", "/admin/organisaties"} <= menu
    assert not {"/admin/organisatie", "/admin/instellingen"} & menu
    for path in ("/admin/tenants", "/admin/organisaties", "/admin/gebruikers/alle-werkruimtes"):
        assert client.get(path).status_code == 200, path
    for path in ("/admin/organisatie", "/admin/instellingen"):
        assert client.get(path).status_code == 404, path
    assert platform_tenant_id(db_session) is not None


def test_changes_and_the_mail_log_are_unaffected(client, db_session):
    _login(client, db_session, "admin-d-1535@example.com", "ADMIN", TENANT_MILLEGEM_ID)
    menu = _menu(client.get("/admin").text)
    for path in ("/admin/ledenwijzigingen", "/admin/e-maillog"):
        assert path in menu
        assert client.get(path).status_code == 200, path
