"""The buyer's self-cancel (CR-21 phase 3, R23/R25/F8): whoever sees the order may
cancel it — the person and his household; another person's order is a 404, a
signed-out visitor is sent to sign in, and a delivered order is refused."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domains.mdm.api import PaymentMethod
from app.domains.pricing.api import add_prices
from app.domains.product.api import ProductStatus, add_variant, create_product, set_status
from app.domains.sales.api import place_order


def _variant(db_session, *, name="T-shirt", size="M", amount="15.00", stock=5):
    from app.domains.stock.api import receive

    product = create_product(db_session, name)
    set_status(db_session, product.id, ProductStatus.ON_SALE)
    variant = add_variant(db_session, product.id, size)
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal(amount),
        member_amount=None,
    )
    receive(db_session, variant.id, quantity=stock)
    db_session.flush()
    return variant


def _order(db_session, items, *, person_id):
    order = place_order(
        db_session,
        person_id=person_id,
        guest_name="",
        guest_email="",
        guest_mobile="",
        method=PaymentMethod.TRANSFER,
        items=items,
        member=False,
    )
    db_session.commit()
    return order


def _sign_in(client, email: str) -> dict[str, str]:
    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value

    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def test_a_buyer_cancels_their_own_order(client, db_session, every_module_on):
    """AC13: the signed-in buyer cancels before delivery — the order leaves the list
    and the stock is free again. The answer is an `HX-Redirect` (the form posts with
    htmx), so the list page is not swapped into the form."""
    from app.domains.sales.api import get_order
    from app.domains.stock.api import available
    from tests.conftest import create_test_family

    m = _variant(db_session, stock=5)
    _owner, owner_person = create_test_family(db_session, email="eigenaar@example.com")
    order = _order(db_session, [(m.id, 1)], person_id=owner_person.id)
    assert available(db_session, m.id) == 4

    headers = {**_sign_in(client, "eigenaar@example.com"), "HX-Request": "true"}
    answer = client.post(
        f"/mijn/aankopen/{order.id}/annuleren", headers=headers, follow_redirects=False
    )
    assert answer.status_code == 204, answer.text[:300]
    assert answer.headers["HX-Redirect"] == "/mijn/aankopen"

    db_session.expire_all()
    assert get_order(db_session, order.id) is None, "the order leaves the lists"
    assert available(db_session, m.id) == 5, "the reservation is free again"


def test_another_persons_order_is_a_404_and_nothing_is_cancelled(
    client, db_session, every_module_on
):
    """T2: a stranger's cancel of another person's order is a 404, and the order
    stays."""
    from app.domains.sales.api import get_order
    from tests.conftest import create_test_family

    m = _variant(db_session, stock=5)
    _owner, owner_person = create_test_family(db_session, email="eigenaar@example.com")
    create_test_family(db_session, email="vreemde@example.com")
    order = _order(db_session, [(m.id, 1)], person_id=owner_person.id)

    headers = _sign_in(client, "vreemde@example.com")
    answer = client.post(
        f"/mijn/aankopen/{order.id}/annuleren", headers=headers, follow_redirects=False
    )
    assert answer.status_code == 404

    db_session.expire_all()
    assert get_order(db_session, order.id) is not None, "nothing is cancelled"


def test_a_signed_out_visitor_is_sent_to_sign_in(client, db_session, every_module_on):
    """T2: a signed-out visitor is sent to sign in, and back to the order page (not
    the POST-only address)."""
    from tests.conftest import create_test_family

    m = _variant(db_session, stock=5)
    _owner, owner_person = create_test_family(db_session, email="eigenaar@example.com")
    order = _order(db_session, [(m.id, 1)], person_id=owner_person.id)

    answer = client.post(f"/mijn/aankopen/{order.id}/annuleren", follow_redirects=False)
    assert answer.status_code == 302
    assert answer.headers["location"] == f"/aanmelden?terug=/mijn/aankopen/{order.id}"


def test_a_household_member_can_cancel(client, db_session, every_module_on):
    """Koen's "1a": whoever sees the order may cancel it — the household included."""
    from app.domains.mdm.api import ContactDetail, MemberPerson
    from app.domains.sales.api import get_order
    from tests.conftest import create_test_family, create_test_person

    m = _variant(db_session, stock=5)
    owner_member, owner_person = create_test_family(db_session, email="eigenaar@example.com")
    partner = create_test_person(db_session)
    db_session.add(
        MemberPerson(member_id=owner_member.id, person_id=partner.id, relation_type="PARTNER")
    )
    db_session.add(
        ContactDetail(
            party_id=partner.party_id, contact_type_code="EMAIL", value="partner@example.com"
        )
    )
    db_session.flush()  # the partner is the test's own seed, before the app commits (#1885)
    order = _order(db_session, [(m.id, 1)], person_id=owner_person.id)

    headers = {**_sign_in(client, "partner@example.com"), "HX-Request": "true"}
    answer = client.post(
        f"/mijn/aankopen/{order.id}/annuleren", headers=headers, follow_redirects=False
    )
    assert answer.status_code == 204, answer.text[:300]

    db_session.expire_all()
    assert get_order(db_session, order.id) is None, "the household member cancels the order"


def test_after_delivery_the_buyer_cannot_cancel(client, db_session, every_module_on):
    """AC14: after a delivery the buyer's cancel is refused in words, and the order
    stays."""
    from app.domains.sales.api import deliver_line, get_order
    from tests.conftest import create_test_family

    m = _variant(db_session, stock=5)
    _owner, owner_person = create_test_family(db_session, email="eigenaar@example.com")
    order = _order(db_session, [(m.id, 1)], person_id=owner_person.id)
    deliver_line(db_session, order.id, order.lines[0].id, actor="verkoper@example.com")
    db_session.commit()

    headers = _sign_in(client, "eigenaar@example.com")
    answer = client.post(
        f"/mijn/aankopen/{order.id}/annuleren", headers=headers, follow_redirects=False
    )
    assert answer.status_code == 422
    assert "geleverd" in answer.text

    db_session.expire_all()
    assert get_order(db_session, order.id) is not None, "the order stays"


def test_the_buyer_reads_bestelling_annuleren_and_verkoop_annuleren(
    client, db_session, every_module_on
):
    """Q61: the words follow who clicks — the buyer "Bestelling annuleren", Verkoop
    "Annuleren" (#2172: the button cancels and refunds, so it says so; it said
    "Verwijderen" before)."""
    from tests.conftest import board_session, create_test_family

    m = _variant(db_session, stock=5)
    _owner, owner_person = create_test_family(db_session, email="eigenaar@example.com")
    order = _order(db_session, [(m.id, 1)], person_id=owner_person.id)

    _sign_in(client, "eigenaar@example.com")
    buyer_page = client.get(f"/mijn/aankopen/{order.id}")
    assert "Bestelling annuleren" in buyer_page.text

    board_session(client)
    admin_page = client.get(f"/admin/verkoop/{order.id}")
    assert ">Annuleren<" in admin_page.text.replace("\n", "").replace("  ", "")
    assert "Verwijderen" not in admin_page.text
    assert "Bestelling annuleren" not in admin_page.text


def test_cancelling_a_paid_order_makes_the_refund_due(client, db_session, every_module_on):
    """T12: a paid order, cancelled by the buyer, makes a refund due."""
    from app.domains.payment.api import PayableType, confirm_manual_payment, get_records_for
    from app.domains.payment.models import PaymentType
    from app.domains.sales.api import submit_order
    from app.kernel.form_guard import TRUSTED
    from tests.conftest import create_test_family, form_guard_fields

    m = _variant(db_session, stock=5)
    _owner, owner_person = create_test_family(db_session, email="eigenaar@example.com")
    _checkout, order_id, _key = submit_order(
        db_session,
        proof=TRUSTED,
        values=form_guard_fields(),
        person_id=owner_person.id,
        member=False,
        contact_name="",
        contact_email="",
        phone="",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 1)],
    )
    (record,) = get_records_for(db_session, PayableType.ORDER, order_id)
    confirm_manual_payment(
        db_session, record.id, amount_paid=record.amount, actor="penning@example.com"
    )
    db_session.commit()

    headers = {**_sign_in(client, "eigenaar@example.com"), "HX-Request": "true"}
    answer = client.post(
        f"/mijn/aankopen/{order_id}/annuleren", headers=headers, follow_redirects=False
    )
    assert answer.status_code == 204

    db_session.expire_all()
    records = get_records_for(db_session, PayableType.ORDER, order_id)
    refunds = [r for r in records if r.type == PaymentType.REFUND]
    assert [r.amount for r in refunds] == [Decimal("-15.00")], "the paid order leaves a refund due"


def test_a_cancel_without_csrf_is_refused_and_nothing_changes(client, db_session, every_module_on):
    """B1: the owner's POST without the CSRF header answers 403 and cancels nothing."""
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from app.domains.sales.api import get_order
    from tests.conftest import create_test_family

    m = _variant(db_session, stock=5)
    _owner, owner_person = create_test_family(db_session, email="eigenaar@example.com")
    order = _order(db_session, [(m.id, 1)], person_id=owner_person.id)

    client.cookies.set(SESSION_COOKIE, make_session_value("eigenaar@example.com"))
    answer = client.post(f"/mijn/aankopen/{order.id}/annuleren", follow_redirects=False)
    assert answer.status_code == 403

    db_session.expire_all()
    assert get_order(db_session, order.id) is not None, "nothing is cancelled"


def test_a_partly_paid_order_does_not_claim_nothing_was_paid(client, db_session, every_module_on):
    """A2: on a partly paid order the cancel confirm says nothing about payment, so it
    cannot claim the buyer paid nothing."""
    from app.domains.payment.api import PayableType, confirm_manual_payment, get_records_for
    from app.domains.sales.api import submit_order
    from app.kernel.form_guard import TRUSTED
    from tests.conftest import create_test_family, form_guard_fields

    m = _variant(db_session, stock=5)
    _owner, owner_person = create_test_family(db_session, email="eigenaar@example.com")
    _checkout, order_id, _key = submit_order(
        db_session,
        proof=TRUSTED,
        values=form_guard_fields(),
        person_id=owner_person.id,
        member=False,
        contact_name="",
        contact_email="",
        phone="",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 2)],
    )
    (record,) = get_records_for(db_session, PayableType.ORDER, order_id)
    confirm_manual_payment(
        db_session, record.id, amount_paid=Decimal("15.00"), actor="penning@example.com"
    )
    db_session.commit()

    _sign_in(client, "eigenaar@example.com")
    page = client.get(f"/mijn/aankopen/{order_id}")
    assert "Bestelling annuleren" in page.text
    assert "nog niets betaald" not in page.text


def test_verkoop_annuleren_on_a_paid_order_names_the_refund(client, db_session, every_module_on):
    """#2172: the button reads "Annuleren" and its question, unchanged, names the amount
    that is paid back. Proven red (put back): a second button "Verwijderen" added in the
    form of `_order_detail.html` → this test and the one above fail."""
    from app.domains.payment.api import PayableType, confirm_manual_payment, get_records_for
    from app.domains.sales.api import submit_order
    from app.kernel.form_guard import TRUSTED
    from tests.conftest import board_session, create_test_family, form_guard_fields

    m = _variant(db_session, stock=5)
    _owner, owner_person = create_test_family(db_session, email="eigenaar@example.com")
    _checkout, order_id, _key = submit_order(
        db_session,
        proof=TRUSTED,
        values=form_guard_fields(),
        person_id=owner_person.id,
        member=False,
        contact_name="",
        contact_email="",
        phone="",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 1)],
    )
    (record,) = get_records_for(db_session, PayableType.ORDER, order_id)
    confirm_manual_payment(
        db_session, record.id, amount_paid=record.amount, actor="penning@example.com"
    )
    db_session.commit()

    board_session(client)
    page = client.get(f"/admin/verkoop/{order_id}").text
    form = page[page.index(f'hx-post="/admin/verkoop/{order_id}/annuleren"') :]
    form = form[: form.index("</form>")]
    assert "Annuleren" in form and "Verwijderen" not in form
    assert "De betaalde € 15,00 wordt terugbetaald." in form
