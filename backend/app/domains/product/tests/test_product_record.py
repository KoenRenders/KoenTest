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


def _save_sizes(client, db_session, every_module_on, product, ordered):
    headers = _operator(client, db_session, every_module_on)
    data: dict = {"name": "T-shirt Raak"}
    order: list[str] = []
    for key, name in ordered:
        order.append(key)
        data[f"v.{key}.name"] = name
    data["v_order"] = order
    return client.post(
        f"/admin/producten/{product.id}", data=data, headers=headers, follow_redirects=False
    )


def test_sizes_are_added_and_renamed_through_the_record(client, db_session, every_module_on):
    from app.domains.product.api import size_of, variants_of

    product = create_product(db_session, "T-shirt Raak")
    m = add_variant(db_session, product.id, "M")

    answer = _save_sizes(
        client, db_session, every_module_on, product, [(str(m.id), "Mx"), ("n1", "L")]
    )
    assert answer.status_code == 303

    variants = variants_of(db_session, product.id)
    assert [size_of(v) for v in variants] == ["Mx", "L"]


def test_removing_a_size_through_the_record(client, db_session, every_module_on):
    from app.domains.product.api import variants_of

    product = create_product(db_session, "T-shirt Raak")
    m = add_variant(db_session, product.id, "M")
    add_variant(db_session, product.id, "L")

    answer = _save_sizes(client, db_session, every_module_on, product, [(str(m.id), "M")])
    assert answer.status_code == 303

    variants = variants_of(db_session, product.id)
    assert [v.id for v in variants] == [m.id]


def test_a_size_renamed_to_nothing_is_refused(client, db_session, every_module_on):
    product = create_product(db_session, "T-shirt Raak")
    m = add_variant(db_session, product.id, "M")

    answer = _save_sizes(client, db_session, every_module_on, product, [(str(m.id), "")])
    assert answer.status_code == 422
    assert "naam" in answer.text


def test_a_second_size_with_the_same_name_is_refused(client, db_session, every_module_on):
    from app.domains.product.api import variants_of

    product = create_product(db_session, "T-shirt Raak")
    m = add_variant(db_session, product.id, "M")

    answer = _save_sizes(
        client, db_session, every_module_on, product, [(str(m.id), "M"), ("n1", "m")]
    )
    assert answer.status_code == 422
    assert "bestaat al" in answer.text
    assert [v.id for v in variants_of(db_session, product.id)] == [m.id]
