"""CR-19 #1495, CR-20 — the operator creates an organisation on /admin/organisaties.

Until CR-20 this created an account: an `ACCOUNT` organisation with a name and a
code. Since CR-20 an organisation is a party, with a name and no code (C4.7);
it is an account once a tenant names it as one, and "Nieuwe tenant" names its
account. The rest is filled in on the organisation screen it lands on. OPERATOR
only, on GET and on POST.

Proven red: against master `ed7f683b` the module does not import (no
`create_account`); with the operator check removed from the POST route, the
admin test fails; with the `is_active` filter removed from `accounts`, the
inactive-account test fails.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    csrf_token_for,
    make_session_value,
)
from app.domains.mdm.api import Organization, Tenant, accounts, create_organization
from tests._sites import new_site
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db_session, *, operator: bool) -> dict:
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()

    def held(role: str):
        return db_session.query(UserRole).filter_by(user_id=user.id, role_code=role)

    if operator and not held("OPERATOR").first():
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
    if not operator:
        held("OPERATOR").delete()
        if not held("ADMIN").first():
            db_session.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db_session.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _named(db_session, name: str) -> list[Organization]:
    return db_session.query(Organization).filter(Organization.name == name).all()


def test_an_operator_creates_an_organisation_and_lands_on_its_screen(
    client, platform_workspace, db_session
):
    headers = _login(client, db_session, operator=True)

    form = client.get("/admin/organisaties/nieuw")
    assert form.status_code == 200, form.text
    assert 'hx-post="/admin/organisaties"' in form.text

    answer = client.post(
        "/admin/organisaties",
        data={"name": "Bakkerij Peeters"},
        headers={**headers, "HX-Request": "true"},
    )
    assert answer.status_code == 204, answer.text

    db_session.expire_all()
    [account] = _named(db_session, "Bakkerij Peeters")
    assert account.is_active
    assert db_session.query(Tenant).filter(Tenant.organization_id == account.id).count() == 0
    assert answer.headers["HX-Redirect"] == f"/admin/organisaties/{account.id}"

    screen = client.get(answer.headers["HX-Redirect"])
    assert screen.status_code == 200 and "Bakkerij Peeters" in screen.text


def test_an_admin_is_refused_on_get_and_on_post(client, platform_workspace, db_session):
    headers = _login(client, db_session, operator=False)

    assert client.get("/admin/organisaties/nieuw").status_code == 403
    answer = client.post("/admin/organisaties", data={"name": "Stiekem"}, headers=headers)
    assert answer.status_code == 403
    db_session.expire_all()
    assert _named(db_session, "Stiekem") == []


def test_an_empty_name_is_refused_with_a_readable_message(client, platform_workspace, db_session):
    before = db_session.query(Organization).count()
    headers = _login(client, db_session, operator=True)

    answer = client.post(
        "/admin/organisaties", data={"name": "  "}, headers={**headers, "HX-Request": "true"}
    )

    assert answer.status_code == 200, "a refusal htmx can swap in"
    assert "Een naam is verplicht." in answer.text
    db_session.expire_all()
    assert db_session.query(Organization).count() == before


def test_new_tenant_offers_the_account_and_hangs_under_it(client, platform_workspace, db_session):
    """An account is offered once a tenant names it (CR-20 F5)."""
    first = new_site(db_session, name="Bakkerij Janssens", code="bakkerij-janssens")
    headers = _login(client, db_session, operator=True)

    form = client.get("/admin/tenants/nieuw").text
    assert re.search(rf'<option value="{first.account_id}"[^>]*>Bakkerij Janssens</option>', form)

    answer = client.post(
        "/admin/tenants",
        data={
            "site_name": "Bakkerij Janssens Site",
            "code": "bakkerij-janssens-site",
            "account_id": str(first.account_id),
            "kind": "BEDRIJF",
        },
        headers=headers,
    )
    assert answer.status_code == 200, answer.text
    db_session.expire_all()
    tenant = db_session.query(Tenant).filter(Tenant.code == "bakkerij-janssens-site").one()
    assert tenant.account_id == first.account_id
    assert tenant.organization_id == first.account_id, "it shows its account's data"


def test_an_inactive_account_takes_no_new_tenant(db_session):
    site = new_site(db_session, name="Gestopt", code="gestopt-1495")
    account = db_session.get(Organization, site.account_id)
    assert account.id in {a.id for a in accounts(db_session)}
    account.is_active = False
    db_session.commit()

    assert account.id not in {a.id for a in accounts(db_session)}


def test_new_tenant_with_a_new_account_and_a_new_organisation(
    client, platform_workspace, db_session
):
    """CR-20 F5 (Koen, 18 October 2026: "3 akkoord" — the form in full in phase
    1): "Nieuwe organisatie…" as the account and as the organisation shown,
    both made with the tenant."""
    headers = _login(client, db_session, operator=True)
    form = client.get("/admin/tenants/nieuw").text
    assert '<option value="nieuw">Nieuwe organisatie…</option>' in form
    assert 'name="new_account_name"' in form and 'name="new_organization_name"' in form

    answer = client.post(
        "/admin/tenants",
        data={
            "code": "merk-nieuw-cr20",
            "kind": "BEDRIJF",
            "account_id": "nieuw",
            "new_account_name": "Holding Nieuw",
            "organization_id": "nieuw",
            "new_organization_name": "Merk Nieuw",
        },
        headers=headers,
    )
    assert answer.status_code == 200, answer.text[-400:]
    db_session.expire_all()
    tenant = db_session.query(Tenant).filter(Tenant.code == "merk-nieuw-cr20").one()
    assert tenant.account.name == "Holding Nieuw"
    assert tenant.organization.name == "Merk Nieuw"


def test_a_refused_tenant_leaves_no_new_organisation(client, platform_workspace, db_session):
    """Everything is checked before an organisation is made. Broken on purpose:
    the code check moved after `_new_party` → an organisation stays behind."""
    new_site(db_session, name="Bestaand", code="bestaat-cr20")
    db_session.commit()
    headers = _login(client, db_session, operator=True)
    before = db_session.query(Organization).count()

    answer = client.post(
        "/admin/tenants",
        data={
            "code": "bestaat-cr20",
            "account_id": "nieuw",
            "new_account_name": "Mag Niet Blijven",
        },
        headers=headers,
    )

    assert answer.status_code == 200 and "Die code bestaat al." in answer.text
    assert 'value="Mag Niet Blijven"' in answer.text, "what was typed stays"
    db_session.expire_all()
    assert db_session.query(Organization).count() == before


def test_the_shown_organisation_follows_the_account(client, platform_workspace, db_session):
    """The field offers the account itself, what its tenants show, and a new one."""
    first = new_site(db_session, name="Firma Getoond", code="getoond-cr20")
    sibling = create_organization(db_session, name="Merk Getoond")
    new_site(db_session, name="Zuster", code="zuster-cr20", account_id=first.account_id)
    db_session.commit()
    _login(client, db_session, operator=True)

    field = client.get(f"/admin/tenants/nieuw/getoond?account_id={first.account_id}").text
    options = re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', field)
    assert options[0] == ("", "Het account zelf")
    assert options[-1] == ("nieuw", "Nieuwe organisatie…")
    assert ("Zuster",) == tuple(name for value, name in options[1:-1] if name == "Zuster")
    assert str(sibling.id) not in {value for value, _name in options}, "named by no tenant"
