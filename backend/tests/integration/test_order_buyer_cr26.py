"""The buyer of an order (CR-26 phase 2, F8, F14; T6-T8, T12-T14).

An order names who it is for (`buyer_party_id`) and copies the buyer. *Voor mezelf*:
the person's own party. *Namens*: the organisation's party, the person who placed it
stays in `person_id`; only at a tenant with the invoices module, and only for an
organisation the person acts for. A guest: no buyer party.

Red proofs (19 October 2026, each put back): the module check left out of
`_buyer_columns` -> the module-off test places the order; the `acts_for` check left
out of `submit_order` -> the no-relation test places it; the copy left out ->
the copy test finds no VAT number on the order.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domains.mdm.api import (
    Organization,
    PaymentMethod,
    Person,
    PostalCode,
    new_contact_detail,
    register_organisation,
)
from app.domains.pricing.api import add_prices
from app.domains.product.api import ProductStatus, add_variant, create_product, set_status
from app.domains.sales.api import SalesError, has_orders, place_order, submit_order
from app.domains.stock.api import receive
from app.kernel import form_guard
from tests.conftest import form_guard_fields

pytestmark = pytest.mark.ui_agnostisch

VAT = "BE0403170701"


def _variant(db) -> int:
    product = create_product(db, "Buyer proef")
    set_status(db, product.id, ProductStatus.ON_SALE)
    variant = add_variant(db, product.id, "M")
    add_prices(
        db,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("10.00"),
        member_amount=None,
    )
    receive(db, variant.id, quantity=20)
    db.commit()
    return variant.id


def _person(db, email="koper-cr26@example.com") -> Person:
    person = Person(first_name="Ko", last_name="Per")
    db.add(person)
    db.flush()
    db.add(new_contact_detail(db, person, "EMAIL", email, is_primary=True, confirmed=True))
    db.commit()
    return person


def _organisation(db, person) -> int:
    if db.query(PostalCode).first() is None:
        db.add(PostalCode(postal_code="2000", municipality="Antwerpen"))
        db.commit()
    form = {
        "name": "Koper BV",
        "vat_number": VAT,
        "street": "Teststraat",
        "house_number": "1",
        "postal_code": db.query(PostalCode).first().postal_code,
    }
    organization_id, _created = register_organisation(db, person.id, form)
    return organization_id


def _place(db, variant_id, person=None, **extra):
    return place_order(
        db,
        person_id=person.id if person else None,
        guest_name="Gast",
        guest_email="gast@example.com",
        guest_mobile="0470000000",
        method=PaymentMethod.TRANSFER,
        items=[(variant_id, 1)],
        member=False,
        **extra,
    )


def test_a_guest_order_has_no_buyer_party(db_session, every_module_on):
    order = _place(db_session, _variant(db_session))
    assert order.buyer_party_id is None and order.buyer_name is None


def test_voor_mezelf_names_the_persons_own_party_and_name(db_session, every_module_on):
    person = _person(db_session)
    order = _place(db_session, _variant(db_session), person)
    assert order.person_id == person.id
    assert order.buyer_party_id == person.party_id
    assert order.buyer_name == "Ko Per"


def test_namens_copies_the_organisation_and_keeps_the_person(db_session, every_module_on):
    person = _person(db_session)
    organization_id = _organisation(db_session, person)
    order = _place(db_session, _variant(db_session), person, buyer_organization_id=organization_id)
    organisation = db_session.get(Organization, organization_id)
    assert order.person_id == person.id, "the person who placed it"
    assert order.buyer_party_id == organisation.party_id
    assert (order.buyer_name, order.buyer_vat_number) == ("Koper BV", VAT)
    assert (order.buyer_street, order.buyer_house_number) == ("Teststraat", "1")
    assert order.buyer_postal_code and order.buyer_municipality and order.buyer_country == "BE"


def test_the_copy_survives_a_change_of_the_organisation(db_session, every_module_on):
    person = _person(db_session)
    organization_id = _organisation(db_session, person)
    order = _place(db_session, _variant(db_session), person, buyer_organization_id=organization_id)
    db_session.get(Organization, organization_id).name = "Nieuwe naam"
    db_session.flush()
    assert order.buyer_name == "Koper BV"


def test_without_the_invoices_module_an_organisation_buyer_is_refused(db_session):
    """The module is off by default (F14): this tenant has not switched it on."""
    person = _person(db_session)
    organization_id = _organisation(db_session, person)
    variant_id = _variant(db_session)
    with pytest.raises(SalesError):
        _place(db_session, variant_id, person, buyer_organization_id=organization_id)


def test_namens_without_the_relation_is_refused(db_session, every_module_on):
    person = _person(db_session)
    organization_id = _organisation(db_session, person)
    stranger = _person(db_session, "vreemd-cr26@example.com")
    with pytest.raises(SalesError):
        submit_order(
            db_session,
            proof=form_guard.TRUSTED,
            values=form_guard_fields(),
            person_id=stranger.id,
            member=False,
            contact_name="",
            contact_email="",
            phone="",
            method=PaymentMethod.TRANSFER,
            items=[(_variant(db_session), 1)],
            buyer_organization_id=organization_id,
        )


def test_has_orders_reads_klant_from_the_facts(db_session, every_module_on):
    person = _person(db_session)
    organization_id = _organisation(db_session, person)
    organisation = db_session.get(Organization, organization_id)
    assert not has_orders(db_session, person.party_id)
    assert not has_orders(db_session, organisation.party_id)
    _place(db_session, _variant(db_session), person, buyer_organization_id=organization_id)
    db_session.commit()
    assert has_orders(db_session, person.party_id), "the person placed it"
    assert has_orders(db_session, organisation.party_id), "the organisation bought"


def _post_basket(client, variant_id, **extra):
    from tests.conftest import form_guard_fields

    data = {
        "variant_id": str(variant_id),
        "quantity": "1",
        "contact_name": "Ko Per",
        "contact_email": "koper-cr26@example.com",
        "phone": "0470000000",
        "payment_method": "transfer",
        **form_guard_fields(),
        **extra,
    }
    return client.post("/webshop/bestellen", data=data, follow_redirects=False)


def _sign_in(client, email="koper-cr26@example.com"):
    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def test_the_door_places_namens_for_an_organisation_the_person_acts_for(
    client, db_session, every_module_on
):
    from app.domains.sales.models import SalesOrder

    person = _person(db_session)
    organization_id = _organisation(db_session, person)
    variant_id = _variant(db_session)
    _sign_in(client)
    answer = _post_basket(client, variant_id, buyer_organization_id=str(organization_id))
    assert answer.status_code == 200, answer.text
    order = db_session.query(SalesOrder).one()
    assert order.buyer_party_id == db_session.get(Organization, organization_id).party_id
    assert order.person_id == person.id


def test_the_door_refuses_namens_for_an_organisation_the_person_does_not_act_for(
    client, db_session, every_module_on
):
    from app.domains.sales.models import SalesOrder

    owner = _person(db_session, "eigenaar-cr26@example.com")
    organization_id = _organisation(db_session, owner)
    _person(db_session)
    variant_id = _variant(db_session)
    _sign_in(client)
    answer = _post_basket(client, variant_id, buyer_organization_id=str(organization_id))
    assert answer.status_code == 422
    assert "namens deze organisatie" in answer.text
    assert db_session.query(SalesOrder).count() == 0
