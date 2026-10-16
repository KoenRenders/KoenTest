"""Webshop-instellingen (R41, R42): the intro text above the Webshop and the
shop's contact persons reach the buyer only — the thank-you page and the order
page, never the Webshop itself."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.pricing.api import add_prices
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


def _sign_in(client, db_session, email: str) -> None:
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def _contact_person(db_session, *, first, last, email, mobile):
    from app.domains.mdm.api import ContactDetail
    from tests.conftest import create_test_person

    person = create_test_person(db_session, first_name=first, last_name=last)
    db_session.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=email))
    db_session.add(ContactDetail(person_id=person.id, contact_type_code="MOBILE", value=mobile))
    db_session.flush()
    return person


def _orderable_variant(db_session):
    from app.domains.stock.api import receive

    product = create_product(db_session, "T-shirt Raak")
    set_status(db_session, product.id, ProductStatus.ON_SALE)
    variant = add_variant(db_session, product.id, "M")
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("15.00"),
        member_amount=None,
    )
    receive(db_session, variant.id, quantity=5)
    db_session.flush()
    return variant


def test_the_intro_is_saved_and_shown_on_the_webshop(client, db_session, every_module_on):
    """R42/AC21: Verkoop sets the intro text; the Webshop shows it."""
    headers = _operator(client, db_session, every_module_on)

    saved = client.post(
        "/admin/verkoop/instellingen",
        data={"action": "save", "intro": "Kledij en spullen van Raak."},
        headers=headers,
        follow_redirects=False,
    )
    assert saved.status_code == 303

    page = client.get("/webshop")
    assert "Kledij en spullen van Raak." in page.text


def test_an_empty_intro_shows_nothing_above_the_webshop(client, db_session, every_module_on):
    """R42: no intro is set, no intro paragraph stands above the articles."""
    _operator(client, db_session, every_module_on)
    _orderable_variant(db_session)

    page = client.get("/webshop")
    assert page.status_code == 200
    assert "T-shirt Raak" in page.text
    # The intro paragraph only renders when there is a text to show.
    assert 'class="mb-4 text-sm text-ink-soft whitespace-pre-line"' not in page.text


def test_the_contact_persons_show_on_the_thank_you_page_not_the_webshop(
    client, db_session, every_module_on
):
    """R41/T21: the buyer's contact persons stand on the thank-you page with their
    own e-mail and mobile, and not on the Webshop."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import place_order

    headers = _operator(client, db_session, every_module_on)
    contact = _contact_person(
        db_session, first="An", last="Contact", email="an@example.com", mobile="0470000000"
    )
    db_session.commit()

    client.post(
        "/admin/verkoop/instellingen",
        data={"action": "add_contact", "person_id": str(contact.id)},
        headers=headers,
        follow_redirects=False,
    )

    variant = _orderable_variant(db_session)
    order = place_order(
        db_session,
        person_id=None,
        guest_name="Bo",
        guest_email="bo@example.com",
        guest_mobile="0470000001",
        method=PaymentMethod.TRANSFER,
        items=[(variant.id, 1)],
        member=False,
    )
    db_session.commit()

    bedankt = client.get(f"/webshop/bedankt?order={order.id}")
    assert "An Contact" in bedankt.text
    assert "an@example.com" in bedankt.text
    assert "0470000000" in bedankt.text

    webshop = client.get("/webshop")
    assert "An Contact" not in webshop.text
    assert "an@example.com" not in webshop.text


def test_the_contact_persons_show_on_the_buyers_order_page(client, db_session, every_module_on):
    """R41/T21: the order page of the buyer shows the contact persons too."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import place_order

    _operator(client, db_session, every_module_on)
    contact = _contact_person(
        db_session, first="An", last="Contact", email="an@example.com", mobile="0470000000"
    )
    variant = _orderable_variant(db_session)
    order = place_order(
        db_session,
        person_id=contact.id,
        guest_name="",
        guest_email="",
        guest_mobile="",
        method=PaymentMethod.TRANSFER,
        items=[(variant.id, 1)],
        member=False,
    )
    db_session.commit()

    from app.domains.sales.api import add_shop_contact

    add_shop_contact(db_session, contact.id)
    db_session.commit()

    _sign_in(client, db_session, "an@example.com")
    page = client.get(f"/mijn/aankopen/{order.id}")
    assert page.status_code == 200
    assert "An Contact" in page.text
    assert "an@example.com" in page.text
    assert "0470000000" in page.text


def test_removing_a_contact_person_takes_it_off_the_pages(client, db_session, every_module_on):
    """R41: a removed contact person is gone from the thank-you page, and the row
    stays soft-deleted (migration 310)."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import add_shop_contact, place_order, shop_contacts

    headers = _operator(client, db_session, every_module_on)
    contact = _contact_person(
        db_session, first="An", last="Contact", email="an@example.com", mobile="0470000000"
    )
    variant = _orderable_variant(db_session)
    order = place_order(
        db_session,
        person_id=None,
        guest_name="Bo",
        guest_email="bo@example.com",
        guest_mobile="0470000001",
        method=PaymentMethod.TRANSFER,
        items=[(variant.id, 1)],
        member=False,
    )
    add_shop_contact(db_session, contact.id)
    db_session.commit()
    contact_id = shop_contacts(db_session)[0].id

    removed = client.post(
        "/admin/verkoop/instellingen",
        data={"action": "remove_contact", "contact_id": str(contact_id)},
        headers=headers,
        follow_redirects=False,
    )
    assert removed.status_code == 303
    assert shop_contacts(db_session) == []

    bedankt = client.get(f"/webshop/bedankt?order={order.id}")
    assert "An Contact" not in bedankt.text

    from app.domains.sales.models import ShopContact

    row = (
        db_session.query(ShopContact)
        .execution_options(include_deleted=True)
        .filter(ShopContact.id == contact_id)
        .one()
    )
    assert row.deleted_at is not None
