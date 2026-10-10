"""Prijsbeheer's screen (CR-21, T4's screen half): a price is set from a date
through the form, and the list shows it. The price semantics themselves are
walked by `tests/integration/test_pricing_rules.py`.
"""

from __future__ import annotations

from datetime import date

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.pricing.api import Price, prices_of
from app.domains.product.api import Product, create_product
from tests.conftest import SEEDED_ADMIN_EMAIL


def _operator(client, db_session, every_module_on) -> dict[str, str]:
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not any(role.role_code.value == "OPERATOR" for role in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db_session.flush()
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


def test_a_price_is_set_from_a_date_through_the_form(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")

    page = client.get(f"/admin/prijzen/{product.id}")
    assert page.status_code == 200

    answer = client.post(
        f"/admin/prijzen/{product.id}",
        data={
            "valid_from": "2026-11-01",
            "variant_id": "",
            "amount": "17",
            "member_amount": "14",
        },
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 303

    prices = prices_of(db_session, product.id)
    assert len(prices) == 2  # regular and member
    assert {p.amount for p in prices} == {17, 14}
