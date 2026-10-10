"""The shop's screens render with data (CR-21, the B1–B7 repairs).

Each test renders the screen through the client and reads the HTML — the way the
browser does — so a bug that only shows once an article exists is caught here and
not in production.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.pricing.api import Price, PriceType, prices_of
from app.domains.product.api import ProductStatus, add_variant, create_product, set_status
from tests.conftest import SEEDED_ADMIN_EMAIL


def _operator(client, db_session, every_module_on) -> dict[str, str]:
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not any(role.role_code.value == "OPERATOR" for role in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db_session.flush()
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


def test_the_product_list_renders_an_article_and_links_to_it(client, db_session, every_module_on):
    _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    add_variant(db_session, product.id, "M")

    page = client.get("/admin/producten")
    assert page.status_code == 200
    assert "T-shirt Raak" in page.text
    assert f'href="/admin/producten/{product.id}"' in page.text
    assert "1 maat" in page.text


def test_the_price_form_accepts_cents(client, db_session, every_module_on):
    _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")

    page = client.get(f"/admin/prijzen/{product.id}")
    assert page.status_code == 200
    assert 'step="0.01"' in page.text


def test_a_second_price_on_the_same_day_is_refused_in_words(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    first = client.post(
        f"/admin/prijzen/{product.id}",
        data={"valid_from": "2026-11-01", "variant_id": "", "amount": "17", "member_amount": "14"},
        headers=headers,
        follow_redirects=False,
    )
    assert first.status_code == 303

    second = client.post(
        f"/admin/prijzen/{product.id}",
        data={"valid_from": "2026-11-01", "variant_id": "", "amount": "18"},
        headers=headers,
        follow_redirects=False,
    )
    assert second.status_code == 422
    assert "staat al een prijs" in second.text


def test_annuleren_leads_back_to_the_record(client, db_session, every_module_on):
    _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")

    record = client.get(f"/admin/producten/{product.id}?bewerken=1")
    assert record.status_code == 200
    assert f'href="/admin/producten/{product.id}"' in record.text

    price = client.get(f"/admin/prijzen/{product.id}")
    assert price.status_code == 200
    assert f'href="/admin/prijzen/{product.id}"' in price.text


def test_geldt_is_per_size_and_type(client, db_session, every_module_on):
    _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    medium = add_variant(db_session, product.id, "M")
    today = date.today()
    db_session.add_all(
        [
            Price(
                product_id=product.id,
                variant_id=None,
                price_type=PriceType.REGULAR,
                amount=Decimal("15.00"),
                valid_from=today - timedelta(days=39),
            ),
            Price(
                product_id=product.id,
                variant_id=medium.id,
                price_type=PriceType.REGULAR,
                amount=Decimal("17.00"),
                valid_from=today - timedelta(days=70),
            ),
        ]
    )
    db_session.flush()

    page = client.get(f"/admin/prijzen/{product.id}")
    assert page.status_code == 200
    assert "Voorbij" not in page.text, "the size's own older price is in force, not superseded"
    assert page.text.count("Vandaag") == 2


def test_a_missing_article_is_404_not_500(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    answer = client.post(
        "/admin/producten/999999/status", data={"status": "ON_SALE"}, headers=headers
    )
    assert answer.status_code == 404


def test_a_size_of_another_article_is_refused(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    shirt = create_product(db_session, "T-shirt Raak")
    sweater = create_product(db_session, "Sweater Raak")
    sweater_size = add_variant(db_session, sweater.id, "M")

    answer = client.post(
        f"/admin/prijzen/{shirt.id}",
        data={
            "valid_from": "2026-11-01",
            "variant_id": str(sweater_size.id),
            "amount": "17",
        },
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert "hoort niet bij dit artikel" in answer.text
    assert prices_of(db_session, shirt.id) == []


def test_a_missing_article_on_update_is_404_not_500(client, db_session, every_module_on):
    headers = _operator(client, db_session, every_module_on)
    answer = client.post(
        "/admin/producten/999999", data={"name": "x"}, headers=headers, follow_redirects=False
    )
    assert answer.status_code == 404


def test_a_delete_with_movements_is_refused_visibly(client, db_session, every_module_on):
    """The delete gate lives in `stock`'s handler (Q75, AC19): an article with a
    movement is refused, and the sentence reaches the record's message line — the
    visible box — not the closed menu that was clicked."""
    from app.domains.stock.api import receive

    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    variant = add_variant(db_session, product.id, "M")
    db_session.add(
        Price(
            product_id=product.id,
            variant_id=None,
            price_type=PriceType.REGULAR,
            amount=Decimal("15.00"),
            valid_from=date(2026, 1, 1),
        )
    )
    db_session.flush()
    receive(db_session, variant.id, quantity=5)

    record = client.get(f"/admin/producten/{product.id}")
    assert 'id="product-melding"' in record.text, "the header names a line the page lacks"

    answer = client.post(
        f"/admin/producten/{product.id}/verwijderen",
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert "voorraadbewegingen" in answer.text
    assert answer.headers.get("HX-Retarget") == "#product-melding"


def _article_with_a_movement(client, db_session, every_module_on):
    """An article with one size and a movement, signed in as the operator."""
    from app.domains.stock.api import receive

    headers = _operator(client, db_session, every_module_on)
    product = create_product(db_session, "T-shirt Raak")
    variant = add_variant(db_session, product.id, "M")
    receive(db_session, variant.id, quantity=5)
    return headers, product


def test_a_refused_delete_offers_afvoeren_while_the_article_is_not_yet_afgevoerd(
    client, db_session, every_module_on
):
    """An article with a movement that is not Afgevoerd is offered the alternative
    (AC19, W23): the sentence carries "— zet het afgevoerd."."""
    headers, product = _article_with_a_movement(client, db_session, every_module_on)
    set_status(db_session, product.id, ProductStatus.ON_SALE)

    answer = client.post(
        f"/admin/producten/{product.id}/verwijderen",
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert "zet het afgevoerd" in answer.text


def test_a_refused_delete_does_not_offer_afvoeren_when_the_article_is_already_afgevoerd(
    client, db_session, every_module_on
):
    """An article already Afgevoerd is told the bare fact, without the offer
    (Koen, 10 October 2026): the sentence ends after "kan niet verwijderd worden."."""
    headers, product = _article_with_a_movement(client, db_session, every_module_on)
    set_status(db_session, product.id, ProductStatus.DISCONTINUED)

    answer = client.post(
        f"/admin/producten/{product.id}/verwijderen",
        headers=headers,
        follow_redirects=False,
    )
    assert answer.status_code == 422
    assert "voorraadbewegingen" in answer.text
    assert "zet het afgevoerd" not in answer.text
