"""Voorraadbeheer's screen (CR-21, T5's screen half): a receipt and a correction
are booked through their forms, and the list shows the figures. The ledger
semantics themselves are walked by `app/domains/stock/tests/test_stock.py`.
"""

from __future__ import annotations

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.product.api import add_variant, create_product
from app.domains.stock.api import on_hand, receive
from tests.conftest import SEEDED_ADMIN_EMAIL


def _operator(client, db_session, every_module_on) -> dict[str, str]:
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not any(role.role_code.value == "OPERATOR" for role in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db_session.flush()
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


def test_the_list_renders_a_size_with_its_figures(client, db_session, every_module_on):
    _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    variant = add_variant(db_session, product.id, "M")
    receive(db_session, variant.id, quantity=10)

    page = client.get("/admin/voorraad")
    assert page.status_code == 200
    assert "T-shirt Raak" in page.text
    assert "M" in page.text
    assert ">10<" in page.text


def test_the_receipt_and_correction_forms_render(client, db_session, every_module_on):
    _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    add_variant(db_session, product.id, "M")

    receipt = client.get("/admin/voorraad/ontvangst")
    assert receipt.status_code == 200
    assert "Artikel en maat" in receipt.text

    correction = client.get("/admin/voorraad/correctie")
    assert correction.status_code == 200
    assert "Richting" in correction.text
    assert "Reden" in correction.text


def test_a_receipt_is_booked_through_the_form(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    variant = add_variant(db_session, product.id, "M")

    answer = client.post(
        "/admin/voorraad/ontvangst",
        data={"variant_id": str(variant.id), "quantity": "10"},
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 303
    assert on_hand(db_session, variant.id) == 10


def test_a_correction_is_booked_through_the_form(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    variant = add_variant(db_session, product.id, "M")
    receive(db_session, variant.id, quantity=10)

    answer = client.post(
        "/admin/voorraad/correctie",
        data={
            "variant_id": str(variant.id),
            "quantity": "2",
            "direction": "down",
            "note": "retour",
        },
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 303
    assert on_hand(db_session, variant.id) == 8


def test_a_correction_without_a_reason_is_refused_in_words(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    variant = add_variant(db_session, product.id, "M")
    receive(db_session, variant.id, quantity=10)

    answer = client.post(
        "/admin/voorraad/correctie",
        data={"variant_id": str(variant.id), "quantity": "2", "direction": "down", "note": ""},
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert "reden" in answer.text
    assert on_hand(db_session, variant.id) == 10
