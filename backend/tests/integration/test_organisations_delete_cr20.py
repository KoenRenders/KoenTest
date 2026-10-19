"""CR-20 phase 2 (#1578): delete a party, the tenants that use it, the Tenants list by account.

C6 tests 3, 4, 5 and 15, and C4.4 as the architecture CLI read it on 19 October
2026 (B9, Q13):

- a party a tenant names — as the organisation it shows or as its account — is
  "in use": Verwijderen refuses, naming those tenants, and nothing changes;
- an unused party goes softly with its `mdm.parties` row and its details
  (addresses, contacts, bank accounts, identifications, relations), with a
  history row where the table has one; nothing is hard-deleted;
- `delete_person` takes the person's party along;
- Organisaties counts the tenants that use each party; Tenants sorts by account;
- test 16: "Onze organisatie" is editable when its party is nobody's account and
  no other tenant shows it (the architecture CLI, 19 October 2026, B9, Q14); a
  party two sites show is read-only at both. The #1550 case — a site that shows
  its account — stays read-only in `test_site_organisation.py`.

Proven red, additively (put back each time): `naming = []` added after the
`tenants_naming` call in `delete_organization` → the refusals delete the
organisation; the bank accounts' and identifications' `soft_delete` replaced by
`continue` → the test names `BankAccount` live; `return` added before `soft_delete(person.party)` in `delete_person`
→ the person's party and relations stay live; `continue` before the relation's
`soft_delete` in `delete_person` → the relation stays live. Test 16 is red on the rule before (`org_id ==
tenant`): a site that shows a new party of its own could not edit it.
"""

from __future__ import annotations

import pytest

from app.domains.mdm.api import (
    Address,
    AddressHistory,
    BankAccount,
    ContactDetail,
    ContactDetailHistory,
    OngeldigeInstelling,
    Organization,
    PartyIdentification,
    Person,
    Tenant,
    create_organization,
    delete_organization,
)
from app.domains.mdm.models import Party, PartyRelationship
from app.domains.reporting.tests.test_reporting_panel_ui import login
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID
from app.kernel.tenant_config import tenant_display_name
from tests._sites import as_account
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_person, seed_postal_code


def _all(db, model, *where):
    db.expire_all()
    return (
        db.query(model)
        .execution_options(include_deleted=True, include_all_tenants=True)
        .filter(*where)
        .all()
    )


def _organisation(db, name="Te Verwijderen vzw"):
    organisation = create_organization(db, name=name)
    db.commit()
    return organisation


def test_a_party_two_tenants_show_refuses_with_both_names(db_session):
    organisation = _organisation(db_session)
    for tenant_id in (TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID):
        db_session.get(Tenant, tenant_id).organization_id = organisation.id
    db_session.commit()
    names = [tenant_display_name(db_session, t) for t in (TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID)]

    with pytest.raises(OngeldigeInstelling) as refused:
        delete_organization(db_session, organisation.id)
    message = refused.value.fouten[""]
    assert all(name in message for name in names), message
    assert _all(db_session, Organization, Organization.id == organisation.id)[0].deleted_at is None


def test_a_party_a_tenant_names_as_its_account_refuses(db_session):
    organisation = _organisation(db_session)
    db_session.get(Tenant, TENANT_VOORBEELD_ID).account_id = as_account(db_session, organisation)
    db_session.commit()

    with pytest.raises(OngeldigeInstelling):
        delete_organization(db_session, organisation.id)
    assert _all(db_session, Party, Party.id == organisation.party_id)[0].deleted_at is None


def test_an_unused_party_goes_softly_with_its_row_and_its_details(db_session):
    postal = seed_postal_code(db_session)
    organisation = _organisation(db_session)
    party, account = organisation.party_id, organisation.account_id
    person = create_test_person(db_session)
    db_session.add_all(
        [
            Address(
                party_id=party,
                account_id=account,
                street="Weg",
                house_number="1",
                postal_code_id=postal.id,
            ),
            ContactDetail(
                party_id=party,
                account_id=account,
                contact_type_code="EMAIL",
                value="weg-cr20@example.org",
                is_primary=True,
            ),
            BankAccount(party_id=party, account_id=account, iban="BE00 0000 0000 2020"),
            PartyIdentification(party_id=party, account_id=account, scheme="VAT", value="BE0"),
            PartyRelationship(
                to_party_id=party, from_party_id=person.party_id, kind="BOARD_MEETING"
            ),
            PartyRelationship(to_party_id=party, from_party_id=person.party_id, kind="ACTS_FOR"),
        ]
    )
    db_session.commit()

    delete_organization(db_session, organisation.id, actor="operator@example.org")

    for model, where in (
        (Organization, Organization.id == organisation.id),
        (Party, Party.id == party),
        (Address, Address.party_id == party),
        (ContactDetail, ContactDetail.party_id == party),
        (BankAccount, BankAccount.party_id == party),
        (PartyIdentification, PartyIdentification.party_id == party),
        (PartyRelationship, PartyRelationship.to_party_id == party),
    ):
        rows = _all(db_session, model, where)
        assert rows and all(r.deleted_at is not None for r in rows), model.__name__
    for history in (AddressHistory, ContactDetailHistory):
        rows = _all(db_session, history, history.party_id == party)
        assert [(r.action, r.actor) for r in rows if r.operation == "delete"] == [
            ("organization_deleted", "operator@example.org")
        ], history.__name__


def test_deleting_a_person_takes_its_party_and_its_relations_along(db_session):
    from app.domains.mdm.service import delete_person

    organisation = _organisation(db_session, "Kring vzw")
    person = create_test_person(db_session)
    db_session.add(
        PartyRelationship(
            to_party_id=organisation.party_id, from_party_id=person.party_id, kind="ACTS_FOR"
        )
    )
    db_session.commit()
    delete_person(db_session, person, actor="bestuur@example.org")
    db_session.commit()
    assert _all(db_session, Person, Person.id == person.id)[0].deleted_at is not None
    assert _all(db_session, Party, Party.id == person.party_id)[0].deleted_at is not None
    relations = _all(
        db_session, PartyRelationship, PartyRelationship.from_party_id == person.party_id
    )
    assert relations and all(r.deleted_at is not None for r in relations)


def test_the_column_and_the_refusal_read_one_rule(platform_workspace, db_session):
    """The count in Organisaties and the refusal of Verwijderen come from one
    place (`tenants_naming_each`): a party a tenant names as its account counts
    there and is refused here."""
    client = platform_workspace
    organisation = _organisation(db_session, "Een Account vzw")
    db_session.get(Tenant, TENANT_VOORBEELD_ID).account_id = as_account(db_session, organisation)
    db_session.commit()
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("OPERATOR",))
    html = client.get("/admin/organisaties?q=Een+Account").text
    row = html[html.index(f'data-organisation="{organisation.id}"') :]
    assert "1 tenant" in row[: row.index("</tr>")]
    with pytest.raises(OngeldigeInstelling):
        delete_organization(db_session, organisation.id)


def test_the_record_refuses_on_its_banner_and_deletes_an_unused_one(platform_workspace, db_session):
    client = platform_workspace
    used = _organisation(db_session, "In Gebruik vzw")
    db_session.get(Tenant, TENANT_VOORBEELD_ID).organization_id = used.id
    unused = _organisation(db_session, "Ongebruikt vzw")
    db_session.commit()
    csrf = login(client, db_session, SEEDED_ADMIN_EMAIL, ("OPERATOR",))
    headers = {"X-CSRF-Token": csrf, "HX-Request": "true"}

    record = client.get(f"/admin/organisaties/{unused.id}").text
    assert f'hx-post="/admin/organisaties/{unused.id}/verwijderen"' in record

    refused = client.post(f"/admin/organisaties/{used.id}/verwijderen", headers=headers)
    assert refused.status_code == 422
    assert tenant_display_name(db_session, TENANT_VOORBEELD_ID) in refused.text
    assert _all(db_session, Organization, Organization.id == used.id)[0].deleted_at is None

    gone = client.post(f"/admin/organisaties/{unused.id}/verwijderen", headers=headers)
    assert gone.status_code == 204 and gone.headers["HX-Redirect"] == "/admin/organisaties"
    assert _all(db_session, Organization, Organization.id == unused.id)[0].deleted_at is not None


def test_organisaties_counts_the_tenants_that_use_a_party(platform_workspace, db_session):
    client = platform_workspace
    organisation = _organisation(db_session, "Twee Sites vzw")
    for tenant_id in (TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID):
        db_session.get(Tenant, tenant_id).organization_id = organisation.id
    db_session.commit()
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("OPERATOR",))
    html = client.get("/admin/organisaties?q=Twee+Sites").text
    row = html[html.index(f'data-organisation="{organisation.id}"') :]
    assert "2 tenants" in row[: row.index("</tr>")]


def test_tenants_are_sorted_by_account_by_default(platform_workspace, db_session):
    client = platform_workspace
    first = _organisation(db_session, "Aaa Account")
    db_session.get(Tenant, TENANT_VOORBEELD_ID).account_id = as_account(db_session, first)
    db_session.commit()
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("OPERATOR",))
    html = client.get("/admin/tenants").text
    voorbeeld = html.index(f'data-tenant="{TENANT_VOORBEELD_ID}"')
    millegem = html.index(f'data-tenant="{TENANT_MILLEGEM_ID}"')
    assert voorbeeld < millegem, "the tenant under the account first in the alphabet comes first"


def _admin_at(client, db, tenant_id: int) -> str:
    from app.domains.auth.api import (
        SESSION_COOKIE,
        User,
        UserRole,
        csrf_token_for,
        make_session_value,
    )

    user = User(email="onze-cr20@example.org", is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN", tenant_id=tenant_id))
    db.commit()
    session = make_session_value(user.email)
    client.cookies.set(SESSION_COOKIE, session)
    return csrf_token_for(session)


def _save_own(client, code: str, csrf: str, name: str):
    return client.post(
        f"/{code}/admin/organisatie",
        data={"name": name},
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )


def test_a_site_that_alone_shows_a_party_of_its_own_edits_it(client, db_session):
    organisation = _organisation(db_session, "Eigen Partij vzw")
    voorbeeld = db_session.get(Tenant, TENANT_VOORBEELD_ID)
    voorbeeld.organization_id = organisation.id
    db_session.commit()
    csrf = _admin_at(client, db_session, voorbeeld.id)

    assert 'id="org-form"' in client.get(f"/{voorbeeld.code}/admin/organisatie?bewerken=1").text
    assert _save_own(client, voorbeeld.code, csrf, "Eigen Partij").status_code == 200
    db_session.expire_all()
    assert db_session.get(Organization, organisation.id).name == "Eigen Partij"


def test_a_party_two_sites_show_is_read_only_at_both(client, db_session):
    organisation = _organisation(db_session, "Gedeelde Partij vzw")
    for tenant_id in (TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID):
        db_session.get(Tenant, tenant_id).organization_id = organisation.id
    db_session.commit()
    voorbeeld = db_session.get(Tenant, TENANT_VOORBEELD_ID)
    csrf = _admin_at(client, db_session, voorbeeld.id)

    page = client.get(f"/{voorbeeld.code}/admin/organisatie?bewerken=1").text
    assert 'id="org-form"' not in page and "Gedeelde Partij vzw" in page
    assert _save_own(client, voorbeeld.code, csrf, "Overgenomen").status_code == 403
    db_session.expire_all()
    assert db_session.get(Organization, organisation.id).name == "Gedeelde Partij vzw"
