"""The article record (CR-21, T1's variants half and T18's screen half).

The record shows an article's sizes and walks its life cycle through the screen:
"In verkoop zetten" (Concept → On sale), "Afvoeren" (→ Discontinued), and the
walk back to Concept is refused by the aggregate. Deleting removes the article.
"""

from __future__ import annotations

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.product.api import ProductStatus, add_variant, create_product, get_product
from tests.conftest import SEEDED_ADMIN_EMAIL


def _operator(client, db_session, every_module_on) -> dict[str, str]:
    """Sign the client in as the seeded admin with OPERATOR, and return the
    headers that carry the CSRF token of that one session value (#1348)."""
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not any(role.role_code.value == "OPERATOR" for role in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db_session.flush()
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


def test_the_record_shows_its_sizes(client, db_session, every_module_on):
    _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    add_variant(db_session, product.id, "M")
    add_variant(db_session, product.id, "L")

    page = client.get(f"/admin/producten/{product.id}")
    assert page.status_code == 200
    assert "T-shirt Raak" in page.text
    assert ">M<" in page.text and ">L<" in page.text


def test_the_life_cycle_walks_through_the_screen(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")

    put = client.post(
        f"/admin/producten/{product.id}/status",
        data={"status": "ON_SALE"},
        headers=headers,
        follow_redirects=False,
    )
    assert put.status_code == 303
    assert get_product(db_session, product.id).status is ProductStatus.ON_SALE

    off = client.post(
        f"/admin/producten/{product.id}/status",
        data={"status": "DISCONTINUED"},
        headers=headers,
        follow_redirects=False,
    )
    assert off.status_code == 303
    assert get_product(db_session, product.id).status is ProductStatus.DISCONTINUED


def test_deleting_from_the_record_removes_the_article(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")

    answer = client.post(
        f"/admin/producten/{product.id}/verwijderen",
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 303
    db_session.expire_all()
    assert get_product(db_session, product.id) is None
