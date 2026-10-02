"""#1494 — the registration card shows the products as the form does.

Every product of the component is a counter row (0 is "not chosen"); one Save
applies the differences — 0 → n adds a line, n → m changes it, n → 0 removes
it — in one transaction with one reconciliation. "Product toevoegen" and
"Verwijderen" are gone. Removing a paid line refuses nothing, as "Verwijderen"
did not either (measured before the build): the payment side prepares the
refund, and the card says so after the save.

Proven red against master `7dc180e0`: the card rendered one counter per chosen
LINE (here 1, not 3), a "— Product toevoegen —" select, and its Save read
`quantity_<item_id>` — so `product_<id>` changed nothing and no refund toast
existed. On this branch: with `set_order_quantities` skipping a 0, the remove
and the refund tests fail.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from app.domains.activities.api import ActivityProduct, Registration, RegistrationItem
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.payment.api import PayableType, confirm_manual_payment, get_records_for
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _admin(client) -> dict:
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


def _three_products(client, db):
    """A component with three paid products, and a registration of one: 1 × the first."""
    activity, component, first = seed_activity_with_product(db, is_free=False, price="10.00")
    second = ActivityProduct(
        component_id=component.id, name="Tweede", price=Decimal("20.00"), is_free=False
    )
    third = ActivityProduct(
        component_id=component.id, name="Derde", price=Decimal("5.00"), is_free=False
    )
    db.add_all([second, third])
    db.commit()
    answer = client.post(
        f"/api/v1/activities/{activity.id}/register",
        json={
            "contact_name": "An Janssens",
            "phone": "0470000000",
            "contact_email": "an@example.com",
            "component_id": component.id,
            "payment_method": "transfer",
            "items": [{"product_id": first.id, "quantity": 1}],
        },
    )
    assert answer.status_code in (200, 201), answer.text
    return answer.json()["id"], (first, second, third)


def _lines(db, reg_id) -> dict[int, int]:
    db.expire_all()
    rows = db.query(RegistrationItem).filter(RegistrationItem.registration_id == reg_id).all()
    return {r.product_id: r.quantity for r in rows}


def test_the_card_shows_every_product_as_a_counter(client, db_session):
    reg_id, (first, second, third) = _three_products(client, db_session)
    _admin(client)
    html = client.get(f"/admin/inschrijvingen/{reg_id}").text

    assert html.count("data-product-row") == 3, "one counter per product of the component"
    values = dict(re.findall(r'name="product_(\d+)"[^>]*value="(\d+)"', html))
    assert values == {str(first.id): "1", str(second.id): "0", str(third.id): "0"}
    assert 'name="product_id"' not in html and "Product toevoegen" not in html
    assert "/verwijderen" not in html.split("data-product-row", 1)[1].split("Opmerking")[0]


def test_one_save_adds_changes_and_removes(client, db_session):
    reg_id, (first, second, third) = _three_products(client, db_session)
    headers = _admin(client)
    answer = client.post(
        f"/admin/inschrijvingen/{reg_id}/opslaan",
        data={f"product_{first.id}": "0", f"product_{second.id}": "2", f"product_{third.id}": "3"},
        headers=headers,
    )
    assert answer.status_code == 200, answer.text
    assert _lines(db_session, reg_id) == {second.id: 2, third.id: 3}
    reg = db_session.get(Registration, reg_id)
    charges = [r for r in get_records_for(db_session, PayableType.REGISTRATION, reg.id)]
    assert sum(Decimal(str(r.amount)) for r in charges) == Decimal("55.00"), "2 × 20 + 3 × 5"


def test_a_paid_product_to_zero_prepares_the_refund_and_says_so(client, db_session):
    reg_id, (first, second, _third) = _three_products(client, db_session)
    record = get_records_for(db_session, PayableType.REGISTRATION, reg_id)[0]
    confirm_manual_payment(db_session, record.id, amount_paid=Decimal("10.00"))
    db_session.commit()
    headers = _admin(client)

    answer = client.post(
        f"/admin/inschrijvingen/{reg_id}/opslaan",
        data={f"product_{first.id}": "0"},
        headers=headers,
    )
    assert answer.status_code == 200, answer.text
    assert "Er staat een terugbetaling van € 10,00 klaar om te bevestigen." in answer.text
    assert _lines(db_session, reg_id) == {}
    refunds = [
        r
        for r in get_records_for(db_session, PayableType.REGISTRATION, reg_id)
        if str(r.type) == "refund" and r.amount_paid is None
    ]
    assert [Decimal(str(r.amount)) for r in refunds] == [Decimal("-10.00")]


def test_a_save_without_a_lower_order_says_nothing_about_a_refund(client, db_session):
    reg_id, (first, _second, _third) = _three_products(client, db_session)
    answer = client.post(
        f"/admin/inschrijvingen/{reg_id}/opslaan",
        data={f"product_{first.id}": "2"},
        headers=_admin(client),
    )
    assert answer.status_code == 200
    assert "De inschrijving is opgeslagen." in answer.text
    assert "terugbetaling" not in answer.text


def test_a_product_of_another_component_is_refused_and_nothing_is_saved(client, db_session):
    reg_id, (first, second, _third) = _three_products(client, db_session)
    _activity, _component, foreign = seed_activity_with_product(db_session, is_free=False)
    answer = client.post(
        f"/admin/inschrijvingen/{reg_id}/opslaan",
        data={f"product_{second.id}": "4", f"product_{foreign.id}": "1"},
        headers=_admin(client),
    )
    assert answer.status_code == 200
    assert "Product hoort niet bij deze activiteit." in answer.text
    assert _lines(db_session, reg_id) == {first.id: 1}, "nothing of the rest was saved"
