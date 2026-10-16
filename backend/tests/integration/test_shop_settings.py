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


def test_a_placed_order_queues_its_confirmation_mail(client, db_session, every_module_on):
    """T14/T15/T21's mail: an order queues a confirmation mail with the order's
    lines and total, the transfer instructions, and the contact persons."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import add_shop_contact, submit_order
    from app.kernel.form_guard import TRUSTED
    from tests._queued_mail import queued_mails
    from tests.conftest import form_guard_fields

    _operator(client, db_session, every_module_on)
    contact = _contact_person(
        db_session, first="An", last="Contact", email="an@example.com", mobile="0470000000"
    )
    add_shop_contact(db_session, contact.id)
    variant = _orderable_variant(db_session)
    db_session.commit()

    submit_order(
        db_session,
        proof=TRUSTED,
        values=form_guard_fields(),
        person_id=None,
        member=False,
        contact_name="Bo",
        contact_email="bo@example.com",
        phone="0470000001",
        method=PaymentMethod.TRANSFER,
        items=[(variant.id, 2)],
    )

    (mail,) = queued_mails(db_session, "bo@example.com")
    assert mail["email_type"] == "order_confirmation"
    assert "Bo" in mail["body_html"]
    assert "T-shirt Raak" in mail["body_html"]
    assert "€ 15,00 per stuk" in mail["body_html"], "the order mail writes amounts with a comma"
    assert "Totaal:</strong> <strong>€ 30,00" in mail["body_html"]
    assert "Betaalinstructies" in mail["body_html"], "the transfer instructions are in the mail"
    assert "An Contact" in mail["body_html"], "the contact persons are in the mail"
    assert "an@example.com" in mail["body_html"]


def test_a_members_mail_link_signs_in_and_lands_on_his_order(client, db_session, every_module_on):
    """F13/Q26: the member's order mail carries the sign-in link, with the order as
    its destination; a guest's mail carries no link."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import submit_order
    from app.kernel.form_guard import TRUSTED
    from tests._queued_mail import queued_link, queued_mails
    from tests.conftest import form_guard_fields

    _operator(client, db_session, every_module_on)
    member = _contact_person(
        db_session, first="An", last="Contact", email="an@example.com", mobile="0470000000"
    )
    variant = _orderable_variant(db_session)
    db_session.commit()

    _checkout, order_id = submit_order(
        db_session,
        proof=TRUSTED,
        values=form_guard_fields(),
        person_id=member.id,
        member=False,
        contact_name="",
        contact_email="",
        phone="",
        method=PaymentMethod.TRANSFER,
        items=[(variant.id, 1)],
    )

    link = queued_link(db_session, "an@example.com")
    assert "/login/verify?token=" in link, "the member's link is the sign-in link"
    assert f"terug=/mijn/aankopen/{order_id}" in link, "the link lands on the order"

    from app.domains.auth.api import consume_link

    token = link.split("token=")[1].split("&")[0]
    consumed = consume_link(db_session, token)
    assert consumed is not None and consumed.email == "an@example.com"
    db_session.commit()

    _sign_in(client, db_session, "an@example.com")
    assert client.get(f"/mijn/aankopen/{order_id}").status_code == 200

    guest_variant = _orderable_variant(db_session)
    _checkout, guest_id = submit_order(
        db_session,
        proof=TRUSTED,
        values=form_guard_fields(),
        person_id=None,
        member=False,
        contact_name="Bo",
        contact_email="bo@example.com",
        phone="0470000001",
        method=PaymentMethod.TRANSFER,
        items=[(guest_variant.id, 1)],
    )
    assert queued_mails(db_session, "bo@example.com")[-1]["body_html"].count("login/verify") == 0, (
        "a guest's mail carries no sign-in link"
    )
    assert client.get(f"/mijn/aankopen/{guest_id}").status_code == 404


def test_an_order_on_a_person_without_an_address_queues_no_mail(
    client, db_session, every_module_on
):
    """B1: an order on a person without a confirmed e-mail queues no mail and does
    not fail."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import submit_order
    from app.kernel.form_guard import TRUSTED
    from tests.conftest import create_test_person, form_guard_fields

    _operator(client, db_session, every_module_on)
    person = create_test_person(db_session, first_name="Geen", last_name="Adres")
    variant = _orderable_variant(db_session)
    db_session.commit()

    before = _mail_count(db_session)
    _checkout, order_id = submit_order(
        db_session,
        proof=TRUSTED,
        values=form_guard_fields(),
        person_id=person.id,
        member=False,
        contact_name="",
        contact_email="",
        phone="",
        method=PaymentMethod.TRANSFER,
        items=[(variant.id, 1)],
    )
    assert _mail_count(db_session) == before, "an order without an address queues no mail"


def _mail_count(db_session) -> int:
    from app.kernel.jobs import KernelJob

    db_session.expire_all()
    return db_session.query(KernelJob).filter(KernelJob.name == "mail.send").count()
