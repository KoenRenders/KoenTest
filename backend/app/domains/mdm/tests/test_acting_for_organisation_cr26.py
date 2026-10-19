"""A person who acts for an organisation (CR-26 phase 2, F7, C4.7; T6-T9, T14).

Red proofs (19 October 2026, each put back): the VAT lookup left out of
`register_organisation` -> the second-person test creates a duplicate; the account
check left out of `act_for` -> the cross-account test links; `end_acts_for` writing
no end date -> the unlink test still lists the organisation; the router included
without `require_module` -> the module-off test answers 200.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import (
    MasterDataError,
    OngeldigeInstelling,
    Organization,
    PartyRelationship,
    Person,
    PostalCode,  # noqa: F401  (the postal code table)
    act_for,
    acts_for,
    end_acts_for,
    new_contact_detail,
    organisation_by_vat,
    organisations_acting_for,
    register_organisation,
)
from app.domains.mdm.tests.test_tenant_modules import EVERY, modules_of  # noqa: F401
from app.kernel.tenancy import TENANT_MILLEGEM_ID

pytestmark = pytest.mark.ui_serverrendered

VAT = "BE0403170701"  # a valid structure: ten digits, check number
ADDRESS = "namens-cr26@example.com"


def _person(db, first="Nam", last="Ens", email=ADDRESS) -> Person:
    person = Person(first_name=first, last_name=last)
    db.add(person)
    db.flush()
    db.add(new_contact_detail(db, person, "EMAIL", email, is_primary=True, confirmed=True))
    db.commit()
    return person


def _form(db, **over):
    postal = db.query(PostalCode).first()
    if postal is None:
        postal = PostalCode(postal_code="2000", municipality="Antwerpen")
        db.add(postal)
        db.commit()
    form = {
        "name": "Proef BV",
        "legal_form": "",
        "vat_number": VAT,
        "street": "Teststraat",
        "house_number": "1",
        "bus_number": "",
        "postal_code": postal.postal_code,
    }
    form.update(over)
    return form


def test_registering_makes_the_organisation_its_vat_its_address_and_the_relation(db_session):
    person = _person(db_session)
    organization_id, created = register_organisation(db_session, person.id, _form(db_session))
    assert created is True
    assert organisation_by_vat(db_session, VAT, account_id=person.account_id) == organization_id
    acting = organisations_acting_for(db_session, person.id)
    assert [(o["id"], o["name"], o["vat_number"]) for o in acting] == [
        (organization_id, "Proef BV", VAT)
    ]
    assert acts_for(db_session, person.id, organization_id)


def test_a_vat_number_with_a_bad_structure_is_refused_before_the_organisation_exists(db_session):
    person = _person(db_session)
    before = db_session.query(Organization).count()
    with pytest.raises(OngeldigeInstelling) as refused:
        register_organisation(db_session, person.id, _form(db_session, vat_number="BE0123456789"))
    assert "vat_number" in refused.value.fouten
    assert db_session.query(Organization).count() == before
    assert organisations_acting_for(db_session, person.id) == []


def test_the_vat_number_is_required(db_session):
    person = _person(db_session)
    with pytest.raises(OngeldigeInstelling) as refused:
        register_organisation(db_session, person.id, _form(db_session, vat_number=""))
    assert set(refused.value.fouten) == {"vat_number"}


def test_a_second_person_on_the_same_vat_number_is_linked_and_edits_nothing(db_session):
    first = _person(db_session)
    second = _person(db_session, "Twee", "De", "tweede-cr26@example.com")
    organization_id, _created = register_organisation(db_session, first.id, _form(db_session))
    again, created = register_organisation(
        db_session, second.id, _form(db_session, name="Andere naam", street="Elders")
    )
    assert (again, created) == (organization_id, False)
    assert db_session.get(Organization, organization_id).name == "Proef BV"
    assert [o["id"] for o in organisations_acting_for(db_session, second.id)] == [organization_id]


def test_acting_for_an_organisation_of_another_account_is_refused(db_session):
    person = _person(db_session)
    organization_id, _created = register_organisation(db_session, person.id, _form(db_session))
    stranger = _person(db_session, "Vreemd", "Eling", "vreemd-cr26@example.com")
    other_account = Organization(name="Andere account", account_id=person.account_id)
    db_session.add(other_account)
    db_session.flush()
    stranger.account_id = other_account.party_id
    db_session.flush()
    with pytest.raises(MasterDataError):
        act_for(db_session, stranger.id, organization_id)
    assert not acts_for(db_session, stranger.id, organization_id)


def test_unlinking_ends_the_relation_and_keeps_the_organisation(db_session):
    person = _person(db_session)
    organization_id, _created = register_organisation(db_session, person.id, _form(db_session))
    assert end_acts_for(db_session, person.id, organization_id, on_day=date(2099, 1, 1)) is True
    assert organisations_acting_for(db_session, person.id) == []
    assert not acts_for(db_session, person.id, organization_id)
    assert db_session.get(Organization, organization_id).deleted_at is None
    relation = db_session.query(PartyRelationship).filter_by(kind="ACTS_FOR").one()
    assert relation.end_date is not None and relation.deleted_at is None
    assert end_acts_for(db_session, person.id, organization_id) is False


def _login(client):
    value = make_session_value(ADDRESS)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def test_the_page_registers_and_lists_and_unlinks(client, db_session, modules_of):  # noqa: F811
    modules_of({TENANT_MILLEGEM_ID: EVERY | {"invoices"}})
    person = _person(db_session)
    headers = _login(client)
    assert "Je bent nog aan geen organisatie gekoppeld." in client.get("/mijn/organisatie").text
    answer = client.post("/mijn/organisatie", data=_form(db_session), headers=headers)
    assert answer.status_code == 200
    assert "Proef BV" in answer.text and VAT in answer.text
    organization_id = organisations_acting_for(db_session, person.id)[0]["id"]
    answer = client.post(f"/mijn/organisatie/{organization_id}/ontkoppelen", headers=headers)
    assert answer.status_code == 200
    assert "Proef BV" not in answer.text


def test_a_refused_registration_answers_422_and_writes_nothing(client, db_session, modules_of):  # noqa: F811
    modules_of({TENANT_MILLEGEM_ID: EVERY | {"invoices"}})
    person = _person(db_session)
    headers = _login(client)
    answer = client.post(
        "/mijn/organisatie", data=_form(db_session, vat_number="BE0123456789"), headers=headers
    )
    assert answer.status_code == 422
    assert organisations_acting_for(db_session, person.id) == []


def test_without_the_invoices_module_the_page_does_not_exist(client, db_session, modules_of):  # noqa: F811
    modules_of({TENANT_MILLEGEM_ID: EVERY})
    _person(db_session)
    _login(client)
    assert client.get("/mijn/organisatie").status_code == 404


def test_the_page_refuses_a_missing_vat_number(client, db_session, modules_of):  # noqa: F811
    """Walks the form of Mijn organisatie (route POST /mijn/organisatie): it posts an
    empty value for `vat_number`, which the browser refuses by `required`; the server
    refuses it too (422, the field named) and writes nothing."""
    modules_of({TENANT_MILLEGEM_ID: EVERY | {"invoices"}})
    person = _person(db_session)
    headers = _login(client)
    data = {**_form(db_session), "vat_number": ""}
    answer = client.post("/mijn/organisatie", data=data, headers=headers)
    assert answer.status_code == 422
    assert organisations_acting_for(db_session, person.id) == []
