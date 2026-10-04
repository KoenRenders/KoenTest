"""#1574 (CR-11 pilot A) — a payments row opens a record page: the booking page.

K2 (#1556) makes the row the way into the record and takes the unfold under a
payments row away. A booking had no record page, so this builds it first:
`/admin/betalingen/<id>`, on the record head of #1557, carrying what the unfold
carried and nothing new — status, amount received, note, "Status verversen",
"Terugbetaling registreren" and "Verwijderen". Every form posts to the route the
unfold posted to (same services, same role rule); `X-Booking-Page` makes the
answer the page again instead of the list.

- The page shows the booking: who, the status as a badge, the context as a jump
  link to its activity (CR-11 Q56), the amounts.
- Each action reaches its service and answers with the page; a refusal shows its
  reason on the page; a delete leads to the way back.
- Who may see payments but not change them sees no action, and a POST is refused.
- The way back is the list as it was left, and a record opened from the page is
  led back to "Betaling van <naam>".

Proven red against master `2c13d319`: there is no such route — every test that
opens the page gets 404 (eight of the nine). On this branch, each on its own:
`X-Booking-Page` ignored in `_uitvoeren` → the action tests fail (the answer is
the list fragment, without a record head); `may_mutate` always true → the
read-only test fails on the primary; the way back built without `terug` → the
way-back test fails; the origin label not knowing a booking page → the last
test fails (the activity is led back to "Betalingen", not to the booking).
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from app.domains.activities.api import Registration
from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

NAME = "Cara Claes"
OGM = "+++111/1111/11111+++"


def _login(client, db, *, finance: bool) -> dict:
    """The seeded admin, with FINANCE — or with neither of the two roles that may
    change payments (FINANCE, OPERATOR), so only ADMIN is left: may see, not change."""
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    has = db.query(UserRole).filter_by(user_id=user.id, role_code="FINANCE").first()
    if finance and not has:
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
    if not finance:
        db.query(UserRole).filter(
            UserRole.user_id == user.id, UserRole.role_code.in_(("FINANCE", "OPERATOR"))
        ).delete(synchronize_session=False)
    db.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value), "HX-Request": "true"}


def _booking(db, *, amount="30.00", status="pending", paid=None, method="transfer"):
    """A registration with one booking, a real name behind it."""
    activity, comp, _product = seed_activity_with_product(db, price=amount)
    reg = Registration(
        contact_email="deelnemer@example.org",
        phone="0470000000",
        activity_id=activity.id,
        component_id=comp.id,
        registration_type="INDIVIDUAL",
        contact_name=NAME,
    )
    db.add(reg)
    db.flush()
    rec = PaymentRecord(
        payable_type="registration",
        payable_id=reg.id,
        amount=Decimal(amount),
        amount_paid=None if paid is None else Decimal(paid),
        method=method,
        status=status,
        structured_communication=OGM,
    )
    db.add(rec)
    db.commit()
    return rec, activity


def _status(rec) -> str:
    return str(getattr(rec.status, "value", rec.status))


def _head(html: str) -> str:
    start = html.index("data-record-head")
    return html[start : html.index("</header>", start)]


def _page_post(client, headers, rec_id, action, data=None, current=None):
    """What a control on the page sends: its route, `X-Booking-Page`, and the
    page's own address as `HX-Current-URL`."""
    return client.post(
        f"/admin/betalingen/{rec_id}/{action}",
        data=data or {},
        headers={
            **headers,
            "X-Booking-Page": str(rec_id),
            "HX-Current-URL": f"http://testserver{current or f'/admin/betalingen/{rec_id}'}",
        },
    )


def test_the_page_shows_the_booking_with_its_context_as_a_jump_link(client, db_session):
    rec, activity = _booking(db_session)
    _login(client, db_session, finance=True)

    answer = client.get(f"/admin/betalingen/{rec.id}")

    assert answer.status_code == 200, answer.text[:300]
    html = answer.text
    head = _head(html)
    assert f"Betaling van {NAME}" in head
    assert "Openstaand" in head and OGM in head
    reference = re.search(r'<a href="([^"]+)" data-reference[^>]*>([^<]+)', head)
    assert reference, "the context is not a jump link"
    assert reference.group(1).startswith(f"/admin/activiteiten/{activity.id}?terug=")
    assert activity.name in reference.group(2)
    figures = html[html.index("data-booking-figures") : html.index("</section>")]
    assert "€ 30,00" in figures
    # Bedrag never coloured; a balance that is not zero in the warning tone.
    assert re.search(r'class="tabular-nums text-ink" data-amount>€ 30,00<', figures)
    assert re.search(r'class="[^"]*text-brand-warning[^"]*" data-balance>€ 30,00<', figures)
    # What the unfold carried: the edit form, and "Bevestig" as the one primary.
    assert 'hx-post="/admin/betalingen/%s/bewerken"' % rec.id in html
    assert "Bevestig" in head
    assert "data-booking-refund" not in html, "a refund form on a booking that is not paid"


def test_an_unknown_booking_is_a_404(client, db_session):
    _login(client, db_session, finance=True)
    answer = client.get("/admin/betalingen/00000000-0000-4000-8000-000000000000")
    assert answer.status_code == 404


def test_bevestig_reaches_the_service_and_answers_with_the_page(client, db_session):
    rec, _activity = _booking(db_session)
    headers = _login(client, db_session, finance=True)

    answer = _page_post(client, headers, rec.id, "bevestigen")

    assert answer.status_code == 200, answer.text[:300]
    db_session.expire_all()
    stored = db_session.get(PaymentRecord, rec.id)
    assert _status(stored) == "paid" and stored.amount_paid == Decimal("30.00")
    head = _head(answer.text)
    assert "Vereffend" in head and "Bevestig" not in head
    assert "data-booking-refund" in answer.text, "a paid charge offers the refund form"


def test_the_edit_form_saves_status_amount_and_note(client, db_session):
    rec, _activity = _booking(db_session)
    headers = _login(client, db_session, finance=True)

    answer = _page_post(
        client,
        headers,
        rec.id,
        "bewerken",
        {"status": "paid", "amount_paid": "12,50", "note": "voorschot"},
    )

    assert answer.status_code == 200, answer.text[:300]
    db_session.expire_all()
    stored = db_session.get(PaymentRecord, rec.id)
    assert stored.amount_paid == Decimal("12.50") and stored.note == "voorschot"
    assert "data-record-head" in answer.text and "voorschot" in answer.text
    assert "Deels betaald" in _head(answer.text)


def test_a_refund_is_registered_on_the_page_and_a_refusal_shows_its_reason(client, db_session):
    rec, _activity = _booking(db_session, status="paid", paid="30.00")
    headers = _login(client, db_session, finance=True)

    # A refusal the service makes before it touches the session ("abc" is no
    # amount): the one over the maximum rolls the session back, and in a test
    # that takes the fixture's uncommitted booking along.
    refused = _page_post(client, headers, rec.id, "refund", {"amount": "abc", "note": ""})
    assert refused.status_code == 200
    assert "data-record-head" in refused.text, "the refusal answered with the list"
    assert re.search(r'role="alert"[^>]*>[^<]*Ongeldig bedrag', refused.text)
    assert db_session.query(PaymentRecord).filter(PaymentRecord.refund_of_id == rec.id).count() == 0

    answer = _page_post(client, headers, rec.id, "refund", {"amount": "10", "note": "annulering"})
    assert answer.status_code == 200, answer.text[:300]
    refund = db_session.query(PaymentRecord).filter(PaymentRecord.refund_of_id == rec.id).one()
    assert refund.amount == Decimal("-10.00")
    # The charge's page lists its refund, as a jump link to the refund's own page.
    listed = answer.text[answer.text.index("data-booking-refunds") :]
    assert f'href="/admin/betalingen/{refund.id}?terug=' in listed

    # The refund's page names the charge it belongs to.
    page = client.get(f"/admin/betalingen/{refund.id}").text
    assert f"Terugbetaling aan {NAME}" in _head(page)
    assert f'href="/admin/betalingen/{rec.id}?terug=' in page


def test_verwijderen_leads_back_to_where_the_page_came_from(client, db_session):
    rec, _activity = _booking(db_session, status="paid", paid="30.00")
    headers = _login(client, db_session, finance=True)
    _page_post(client, headers, rec.id, "refund", {"amount": "10", "note": "annulering"})
    refund = db_session.query(PaymentRecord).filter(PaymentRecord.refund_of_id == rec.id).one()
    page = f"/admin/betalingen/{refund.id}?terug=/admin/betalingen%3Fzicht%3Dopenstaand"
    assert "Verwijderen" in _head(client.get(page).text)

    answer = _page_post(client, headers, refund.id, "verwijderen", current=page)

    assert answer.status_code == 204
    assert answer.headers.get("HX-Redirect") == "/admin/betalingen?zicht=openstaand"
    db_session.expire_all()
    assert db_session.query(PaymentRecord).filter(PaymentRecord.id == refund.id).count() == 0


def test_who_may_not_change_payments_sees_no_action_and_a_post_is_refused(client, db_session):
    rec, _activity = _booking(db_session)
    headers = _login(client, db_session, finance=False)

    answer = client.get(f"/admin/betalingen/{rec.id}")

    assert answer.status_code == 200, "who may see the payments list may see the page"
    html = answer.text
    assert f"Betaling van {NAME}" in _head(html)
    for piece in ("Bevestig", "data-actions-trigger", "<button"):
        assert piece not in _head(html), piece
    assert "data-booking-edit" not in html and "<form" not in html.split("data-record-head")[1]
    for action, data in (
        ("bevestigen", {}),
        ("bewerken", {"status": "paid"}),
        ("refund", {"amount": "5"}),
        ("verwijderen", {}),
    ):
        assert _page_post(client, headers, rec.id, action, data).status_code == 403, action
    db_session.expire_all()
    assert _status(db_session.get(PaymentRecord, rec.id)) == "pending"


def _way_back(html: str) -> tuple[str, str]:
    link = re.search(r'<a data-way-back href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
    assert link, "the page has no way back"
    return link.group(1).replace("&amp;", "&"), re.sub(r"<[^>]+>|\s+", " ", link.group(2)).strip()


def test_the_way_back_is_the_list_as_it_was_left_also_after_a_save(client, db_session):
    rec, _activity = _booking(db_session)
    headers = _login(client, db_session, finance=True)

    assert _way_back(client.get(f"/admin/betalingen/{rec.id}").text) == (
        "/admin/betalingen",
        "Betalingen",
    )
    page = f"/admin/betalingen/{rec.id}?terug=/admin/betalingen%3Fzicht%3Dopenstaand%26q%3Dcara"
    left = ("/admin/betalingen?zicht=openstaand&q=cara", "Betalingen")
    assert _way_back(client.get(page).text) == left

    after = _page_post(client, headers, rec.id, "bewerken", {"note": "x"}, current=page)
    assert _way_back(after.text) == left, "a save on the page lost the way back"
    # Not an open redirect: a way back that is not a local path is refused.
    foreign = client.get(f"/admin/betalingen/{rec.id}?terug=https://elders.example").text
    assert _way_back(foreign)[0] == "/admin/betalingen"


def test_a_record_opened_from_the_page_is_led_back_to_the_booking(client, db_session):
    rec, activity = _booking(db_session)
    _login(client, db_session, finance=True)
    page = client.get(f"/admin/betalingen/{rec.id}").text
    link = re.search(r'<a href="(/admin/activiteiten/[^"]+)" data-reference', _head(page))

    activity_page = client.get(link.group(1).replace("&amp;", "&"))

    assert activity_page.status_code == 200
    href, label = _way_back(activity_page.text)
    assert href == f"/admin/betalingen/{rec.id}"
    assert label == f"Betaling van {NAME}"
