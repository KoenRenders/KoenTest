"""#1550 (CR-19) — a tenant's site may show another organisation of its account.

By default a tenant shows its own organisation row. The operator may point it at
its account, or at another organisation of that account, never at one of another
account. One resolver (`site_organization_id`) feeds the footer, the bank account
in the mails and "Onze organisatie", which shows that organisation read-only; its
data is never copied.

Red against master: there was no choice, the footer always showed the tenant's
own row, and "Onze organisatie" edited it.
"""

from __future__ import annotations

import logging

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.mdm.api import (
    Organization,
    create_account,
    save_organization,
)
from app.kernel.tenancy import TENANT_VOORBEELD_ID
from tests.conftest import seed_postal_code

pytestmark = pytest.mark.ui_serverrendered

IBAN = "BE71 0961 2345 6769"


def _login(client, db, email: str, role: str, tenant_id: int | None) -> str:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code=role, tenant_id=tenant_id))
    db.commit()
    session = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, session)
    return csrf_token_for(session)


def _brand(db):
    """An account with its data, and a tenant under it. The tenant is the seeded
    Voorbeeldafdeling, moved under the account: a tenant created in a test is not
    in the middleware's code cache, which reads through a session of its own, so
    its prefix would answer 404."""
    seed_postal_code(db, "2400", "Mol")
    account = create_account(db, name="Account Acht", code="acht-1550")
    db.commit()
    save_organization(
        db,
        account.id,
        {
            "name": "Account Acht",
            "street": "Achtstraat",
            "house_number": "8",
            "postal_code": "2400",
        },
    )
    from app.domains.mdm.api import update_organization_details

    update_organization_details(db, account.id, {"payment_iban": IBAN})
    brand = db.get(Organization, TENANT_VOORBEELD_ID)
    brand.parent_id = account.id
    db.commit()
    return account, brand


def _footer(client, code: str) -> str:
    html = client.get(f"/{code}/").text
    # The prefix sets the workspace cookie (#889); the next request stands on its own.
    client.cookies.delete("raak_tenant")
    return html[html.index("<footer") : html.index("</footer>")]


def test_a_brand_shows_its_accounts_data_and_nothing_is_copied(
    client, platform_workspace, db_session, caplog
):
    account, brand = _brand(db_session)
    from app.domains.mdm.api import organization_address
    from app.kernel.tenant_config import tenant_payment_iban

    own_street = organization_address(db_session, brand.id).get("street")
    assert "Achtstraat" not in _footer(client, brand.code)
    csrf = _login(client, db_session, "operator-1550@example.com", "OPERATOR", None)

    editor = client.get(f"/admin/tenants/{brand.id}").text
    assert 'name="site_organization_id"' in editor
    assert f'<option value="{account.id}">Account Acht</option>' in editor

    with caplog.at_level(logging.INFO, logger="app.domains.mdm.tenant_service"):
        saved = client.post(
            f"/admin/tenants/{brand.id}",
            data={"site_organization_id": str(account.id)},
            headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
        )
    assert saved.status_code == 200, saved.text[-400:]
    db_session.expire_all()
    assert db_session.get(Organization, brand.id).site_organization_id == account.id
    from app.kernel.tenant_config import site_organization_id

    assert site_organization_id(db_session, brand.id) == account.id
    assert tenant_payment_iban(db_session, brand.id) == IBAN, "the bank account in the mails"
    assert any(
        "tenant site organisation changed" in r.getMessage() and "-> acht-1550" in r.getMessage()
        for r in caplog.records
    )

    footer = _footer(client, brand.code)
    assert "Achtstraat 8" in footer and IBAN in footer

    save_organization(
        db_session,
        account.id,
        {
            "name": "Account Acht",
            "street": "Nieuwstraat",
            "house_number": "9",
            "postal_code": "2400",
        },
    )
    footer = _footer(client, brand.code)
    assert "Nieuwstraat 9" in footer and "Achtstraat" not in footer, "read, not copied"
    assert organization_address(db_session, brand.id).get("street") == own_street, (
        "nothing copied onto the tenant's own row"
    )


def test_an_organisation_of_another_account_is_refused(client, platform_workspace, db_session):
    _account, brand = _brand(db_session)
    other = create_account(db_session, name="Account Negen", code="negen-1550")
    db_session.commit()
    csrf = _login(client, db_session, "operator2-1550@example.com", "OPERATOR", None)

    refused = client.post(
        f"/admin/tenants/{brand.id}",
        data={"site_organization_id": str(other.id)},
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    assert refused.status_code == 422
    assert "Kies een organisatie van het eigen account." in refused.text
    db_session.expire_all()
    assert db_session.get(Organization, brand.id).site_organization_id is None


def test_a_tenant_without_a_choice_is_as_before(client, db_session):
    """A guard, green on master too: Raak Millegem's footer is its own."""
    html = client.get("/").text
    footer = html[html.index("<footer") : html.index("</footer>")]
    assert "Raak Millegem" in footer


def test_onze_organisatie_shows_the_account_read_only(client, db_session):
    account, brand = _brand(db_session)
    setattr(brand, "site_organization_id", account.id)
    db_session.commit()
    csrf = _login(client, db_session, "admin-1550@example.com", "ADMIN", brand.id)

    page = client.get(f"/{brand.code}/admin/organisatie").text
    assert "Deze site toont de gegevens van Account Acht." in page
    assert "<fieldset" in page and "disabled" in page.split("<fieldset", 1)[1].split(">", 1)[0]
    assert 'value="Achtstraat"' in page
    assert ">Opslaan<" not in page.split('id="org-form"', 1)[1]

    refused = client.post(
        f"/{brand.code}/admin/organisatie",
        data={"name": "Overgenomen"},
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    assert refused.status_code == 403
    db_session.expire_all()
    assert db_session.get(Organization, account.id).name == "Account Acht"
