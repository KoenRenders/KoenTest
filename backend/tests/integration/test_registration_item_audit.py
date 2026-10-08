"""Audit + bewerk-pad voor bestelregels (#84).

Wijzigingen aan een bestelling ná inschrijving/betaling (product wisselen, aantal
aanpassen, regel toevoegen/verwijderen) moeten auditeerbaar zijn én het
verschuldigde totaal herberekenen, zodat het saldo in het betaalscherm klopt en
een eventueel terug te betalen bedrag zichtbaar wordt.
"""

from decimal import Decimal

import pytest

from app.domains.activities import service as activities_service
from app.domains.activities.api import (
    ActivityProduct,
    Registration,
    RegistrationItem,
    RegistrationItemHistory,
)
from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    csrf_token_for,
    make_session_value,
)
from app.domains.payment.api import (
    PayableType,
    PaymentRecord,
    PaymentStatus,
    PaymentType,
    registration_balance,
)
from tests import payments_door
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    add_order_line,
    register_at_the_door,
    remove_order_line,
    seed_activity_with_product,
)


def _add_product(db, comp, *, name, price, is_free=False):
    p = ActivityProduct(component_id=comp.id, name=name, price=Decimal(str(price)), is_free=is_free)
    db.add(p)
    db.flush()
    return p


def _register(client, db, comp, product, qty=1):
    activity_id = comp.activity_id
    resp = register_at_the_door(
        client,
        activity_id,
        json={
            "contact_name": "An Janssens",
            "phone": "0470000000",
            "contact_email": "an@example.com",
            "component_id": comp.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": qty}],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    reg = (
        db.query(Registration)
        .filter(Registration.component_id == comp.id)
        .order_by(Registration.id.desc())
        .first()
    )
    item = db.query(RegistrationItem).filter(RegistrationItem.registration_id == reg.id).first()
    return activity_id, reg, item


def _history_for(db, item_id):
    return (
        db.query(RegistrationItemHistory)
        .filter(RegistrationItemHistory.registration_item_id == item_id)
        .order_by(RegistrationItemHistory.id)
        .all()
    )


def test_initial_registration_is_audited(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    _, _reg, item = _register(client, db_session, comp, product)
    rows = _history_for(db_session, item.id)
    assert len(rows) == 1
    assert rows[0].operation == "insert"
    assert rows[0].action == "order_created"
    assert rows[0].source == "registration"
    assert rows[0].quantity == 1
    assert rows[0].product_id == product.id


def test_update_quantity_recomputes_due_and_audits(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, item = _register(client, db_session, comp, product)

    changed = activities_service.update_order_line(
        db_session, activity_id, reg.id, item.id, quantity=2, actor=SEEDED_ADMIN_EMAIL
    )
    assert changed is not None
    assert Decimal(str(registration_balance(db_session, reg)["total_due"])) == Decimal("36.00")

    rows = _history_for(db_session, item.id)
    assert [r.action for r in rows] == ["order_created", "order_changed"]
    assert rows[-1].operation == "update"
    assert rows[-1].quantity == 2
    assert rows[-1].source == "admin_manual"


def test_swap_to_helper_product_auto_refunds(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    helper = _add_product(db_session, comp, name="Vlees - helper", price="0", is_free=True)
    activity_id, reg, item = _register(client, db_session, comp, product)

    # Penningmeester bevestigt de overschrijving van €18.
    charge = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
        )
        .first()
    )
    payments_door.update(client, charge.id, {"status": "paid", "amount_paid": "18.00"})

    # Bestelregel naar de gratis helper-variant → verschuldigd 0; de €18 wordt als
    # terugbetaal-verplichting aangemaakt (#216), pending tot bevestiging.
    changed = activities_service.update_order_line(
        db_session, activity_id, reg.id, item.id, product_id=helper.id, actor=SEEDED_ADMIN_EMAIL
    )
    assert changed is not None
    balance = registration_balance(db_session, reg)
    assert Decimal(str(balance["total_due"])) == Decimal("0.00")
    assert Decimal(str(balance["balance"])) == Decimal("-18.00")
    assert Decimal(str(balance["total_refunded"])) == Decimal("0.00")

    # Penningmeester bevestigt de terugstorting → nu pas vereffend.
    refund = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
            PaymentRecord.type == PaymentType.REFUND,
        )
        .order_by(PaymentRecord.created_at.desc())
        .first()
    )
    assert refund.status == PaymentStatus.PENDING and refund.amount_paid is None
    payments_door.update(client, refund.id, {"status": "paid"})
    bal = payments_door.balance(client, reg.id).json()
    assert Decimal(str(bal["balance"])) == Decimal("0.00")
    assert Decimal(str(bal["total_refunded"])) == Decimal("18.00")


def test_add_order_line(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="5.00")
    activity_id, reg, _item = _register(client, db_session, comp, product)

    assert add_order_line(db_session, activity_id, reg.id, extra.id, 2) is not None
    # 18 + 2×5
    assert Decimal(str(registration_balance(db_session, reg)["total_due"])) == Decimal("28.00")

    new_item = (
        db_session.query(RegistrationItem)
        .filter(
            RegistrationItem.registration_id == reg.id,
            RegistrationItem.product_id == extra.id,
        )
        .first()
    )
    rows = _history_for(db_session, new_item.id)
    assert rows[0].operation == "insert"
    assert rows[0].action == "order_changed"


def test_delete_order_line_audited_before_delete(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, item = _register(client, db_session, comp, product)
    item_id = item.id

    assert remove_order_line(db_session, activity_id, reg.id, item_id) is not None
    # Regel weg, maar de delete-snapshot bleef bestaan (overleeft de bron).
    assert db_session.query(RegistrationItem).filter(RegistrationItem.id == item_id).first() is None
    rows = _history_for(db_session, item_id)
    assert rows[-1].operation == "delete"
    assert rows[-1].action == "order_changed"
    assert rows[-1].quantity == 1  # toestand op moment van verwijderen


def test_product_from_other_activity_rejected(client, db_session):
    _, comp_a, product_a = seed_activity_with_product(db_session, price="18.00")
    _, _comp_b, product_b = seed_activity_with_product(db_session, price="9.00")
    activity_id, reg, item = _register(client, db_session, comp_a, product_a)

    with pytest.raises(activities_service.ActiviteitFout, match="hoort niet bij deze activiteit"):
        activities_service.update_order_line(
            db_session,
            activity_id,
            reg.id,
            item.id,
            product_id=product_b.id,
            actor=SEEDED_ADMIN_EMAIL,
        )
    db_session.refresh(item)
    assert item.product_id == product_a.id


def test_registrations_expose_item_id(client, db_session):
    """De registratielijst van het beheer geeft het item-id mee, zodat de UI regels
    kan bewerken (#84)."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, item = _register(client, db_session, comp, product)
    items = activities_service.registrations_for(db_session, activity_id)[0]["items"]
    assert items[0]["id"] == item.id


def test_the_registration_screens_refuse_an_account_without_the_board_role(client, db_session):
    """Changing a line, the remark and deleting are the board's. The three JSON
    routes each had a "requires admin" test until CR-13 phase 4b (#1251) pruned
    them; the screens that remain are held here, with a signed-in account that
    has a valid CSRF token and only the treasurer's role — so it is the role
    that refuses, not the missing session.

    Broken to see it red: the `Depends(require_admin_ui)` of
    `inschrijving_regel_bijwerken` replaced by a plain default — the answer is no
    longer 403 and the quantity becomes 2.
    """
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, item = _register(client, db_session, comp, product)
    treasurer = User(email="fin-only-1251@example.com", is_active=True)
    db_session.add(treasurer)
    db_session.flush()
    db_session.add(UserRole(user_id=treasurer.id, role_code="FINANCE"))
    db_session.commit()
    session = make_session_value(treasurer.email)
    client.cookies.set(SESSION_COOKIE, session)
    headers = {"X-CSRF-Token": csrf_token_for(session)}

    answers = {
        "line": client.post(
            f"/admin/inschrijvingen/{reg.id}/regels/{item.id}",
            data={"quantity": "2"},
            headers=headers,
        ),
        "remark": client.post(
            f"/admin/inschrijvingen/{reg.id}/opmerking", data={"remarks": "x"}, headers=headers
        ),
        "delete": client.post(
            f"/admin/activiteiten/{activity_id}/inschrijvingen/{reg.id}/verwijderen",
            headers=headers,
        ),
    }

    assert {what: answer.status_code for what, answer in answers.items()} == {
        "line": 403,
        "remark": 403,
        "delete": 403,
    }
    db_session.expire_all()
    assert db_session.get(RegistrationItem, item.id).quantity == 1
    kept = db_session.get(Registration, reg.id)
    assert kept is not None and kept.remarks is None
