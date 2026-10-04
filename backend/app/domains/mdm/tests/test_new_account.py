"""CR-19 #1495 — the operator creates an account on /admin/organisaties.

An account is an `ACCOUNT` organisation: the legal entity tenants hang under. A
root like "raak" (no parent, beside the platform), with only a name and a code;
the rest is filled in on the organisation screen it lands on. OPERATOR only, on
GET and on POST. "Nieuwe tenant" then offers it, and a tenant created under it
has it as parent.

Proven red: against master `ed7f683b` the module does not import (no
`create_account`); with the operator check removed from the POST route, the
admin test fails; with the `is_active` filter removed from `list_accounts`, the
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
from app.domains.mdm.api import (
    Organization,
    OrganizationType,
    create_account,
    list_accounts,
)
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


def _accounts(db_session, code: str) -> list[Organization]:
    return db_session.query(Organization).filter(Organization.code == code).all()


def test_an_operator_creates_an_account_and_lands_on_its_screen(
    client, platform_workspace, db_session
):
    headers = _login(client, db_session, operator=True)

    form = client.get("/admin/organisaties/nieuw")
    assert form.status_code == 200, form.text
    assert 'hx-post="/admin/organisaties"' in form.text

    answer = client.post(
        "/admin/organisaties",
        data={"name": "Bakkerij Peeters", "code": "bakkerij-peeters"},
        headers={**headers, "HX-Request": "true"},
    )
    assert answer.status_code == 204, answer.text

    db_session.expire_all()
    [account] = _accounts(db_session, "bakkerij-peeters")
    assert account.org_type is OrganizationType.ACCOUNT
    assert account.parent_id is None, "a root, like raak"
    assert account.is_active
    assert answer.headers["HX-Redirect"] == f"/admin/organisaties/{account.id}"

    screen = client.get(answer.headers["HX-Redirect"])
    assert screen.status_code == 200 and "Bakkerij Peeters" in screen.text


def test_an_admin_is_refused_on_get_and_on_post(client, platform_workspace, db_session):
    headers = _login(client, db_session, operator=False)

    assert client.get("/admin/organisaties/nieuw").status_code == 403
    answer = client.post(
        "/admin/organisaties", data={"name": "Stiekem", "code": "stiekem"}, headers=headers
    )
    assert answer.status_code == 403
    db_session.expire_all()
    assert _accounts(db_session, "stiekem") == []


@pytest.mark.parametrize("code", ["dubbel-1495", "raakmillegem"])
def test_a_code_that_exists_is_refused_with_a_readable_message(
    client, platform_workspace, db_session, code
):
    """Unique over every organisation: another account's code and a tenant's."""
    if code == "dubbel-1495":
        create_account(db_session, name="Eerste", code=code)
    before = db_session.query(Organization).count()
    headers = _login(client, db_session, operator=True)

    answer = client.post(
        "/admin/organisaties",
        data={"name": "Tweede", "code": code},
        headers={**headers, "HX-Request": "true"},
    )

    assert answer.status_code == 200, "a refusal htmx can swap in"
    assert "Die code bestaat al." in answer.text
    assert 'value="Tweede"' in answer.text, "what was typed stays"
    db_session.expire_all()
    assert db_session.query(Organization).count() == before


def test_new_tenant_offers_the_account_and_hangs_under_it(client, platform_workspace, db_session):
    account = create_account(db_session, name="Bakkerij Janssens", code="bakkerij-janssens")
    headers = _login(client, db_session, operator=True)

    form = client.get("/admin/tenants/nieuw").text
    assert re.search(rf'<option value="{account.id}"[^>]*>Bakkerij Janssens</option>', form)

    answer = client.post(
        "/admin/tenants",
        data={
            "name": "Bakkerij Janssens Site",
            "code": "bakkerij-janssens-site",
            "account_id": str(account.id),
            "kind": "BEDRIJF",
        },
        headers=headers,
    )
    assert answer.status_code == 200, answer.text
    db_session.expire_all()
    [tenant] = _accounts(db_session, "bakkerij-janssens-site")
    assert tenant.parent_id == account.id


def test_an_inactive_account_takes_no_new_tenant(db_session):
    account = create_account(db_session, name="Gestopt", code="gestopt-1495")
    account.is_active = False
    db_session.commit()

    assert account.id not in {a.id for a in list_accounts(db_session)}
