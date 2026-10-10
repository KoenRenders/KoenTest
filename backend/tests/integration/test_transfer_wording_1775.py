"""#1775 — how to pay by transfer is said once, in the mail and on the screen.

Until #1775 the confirmation mail and the screen each wrote the transfer in
their own words ("Rekeningnummer" / "IBAN", "Gestructureerde mededeling" /
"Mededeling (OGM)", a date only in the mail) and each read the settings their
own way. Now both render `payment.api.transfer_due(...).lines`. This is the
issue's own test: **for one unpaid registration and one unpaid membership, the
mail and the screen show the same five lines with the same values**, in the
words Koen fixed on 8 October 2026.

Red (each restored after): the mail block skipping the last line
(`transfer.lines[:-1]`) → mail and screen differ; the partial writing a word of
its own beside the label → they differ; the day taken from today plus the term
instead of from the booking → the third test names another day; a transfer
recognised by the text "transfer" again → no block anywhere (the fault that
emptied the mail's block since CR-12 phase 1, see the first commit of #1775).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html import unescape

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.payment.api import PaymentRecord, transfer_due
from tests.conftest import create_test_family, register_at_the_door, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

LABELS = ["Bedrag", "IBAN", "Begunstigde", "Gestructureerde mededeling", "Te betalen vóór"]
IBAN, HOLDER = "BE00 0000 0000 0000", "Voorbeeldvereniging"


@pytest.fixture(autouse=True)
def account(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "payment_iban", IBAN)
    monkeypatch.setattr(settings, "payment_beneficiary", HOLDER)


@pytest.fixture
def sent(monkeypatch):
    from app.domains.mail import service

    captured: list[dict] = []

    def _capture(to_email, subject, body_html, cc=None, email_type="other"):
        captured.append({"body": body_html, "type": email_type})

    monkeypatch.setattr(service, "_send", _capture)
    return captured


def _mail_lines(body: str) -> list[tuple[str, str]]:
    block = body[body.index("Betaalinstructies (overschrijving)") :]
    block = block[: block.index("</ul>")]
    found = re.findall(r"<li><strong>([^<]+):</strong>\s*([^<]*)</li>", block)
    return [(unescape(label), unescape(value).strip()) for label, value in found]


def _screen_lines(html: str) -> list[tuple[str, str]]:
    start = html.index("data-transfer-due")
    block = html[start : html.index("</ul>", start)]
    found = re.findall(r"<li>([^:<]+):\s*(?:<strong>)?([^<]*?)(?:</strong>)?\s*</li>", block)
    return [(unescape(label).strip(), unescape(value).strip()) for label, value in found]


def _sign_in(client, email: str) -> None:
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def _run_queue(db) -> None:
    from app.kernel.jobs import run_due_jobs

    run_due_jobs(db)


def test_a_registration_reads_the_same_in_the_mail_and_under_mijn_inschrijvingen(
    client, db_session, sent
):
    email = "overschrijving-1775@example.com"
    create_test_family(db_session, email=email, mobile="0470000000")
    activity, component, product = seed_activity_with_product(db_session, price="12.50")
    db_session.commit()
    answer = register_at_the_door(
        client,
        activity.id,
        json={
            "contact_name": "Proef Overschrijving",
            "contact_email": email,
            "phone": "0470000000",
            "component_id": component.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": 2}],
        },
        member_email=email,
    )
    assert answer.status_code == 200, answer.text
    _run_queue(db_session)
    mail = _mail_lines(next(m["body"] for m in sent if m["type"] == "activity_confirmation"))

    _sign_in(client, email)
    screen = _screen_lines(client.get("/mijn/inschrijvingen").text)

    assert [label for label, _value in mail] == LABELS
    assert mail == screen
    values = dict(mail)
    assert values["Bedrag"] == "€ 25,00" and values["IBAN"] == IBAN
    assert values["Begunstigde"] == HOLDER
    assert re.fullmatch(r"\+\+\+\d{3}/\d{4}/\d{5}\+\+\+", values["Gestructureerde mededeling"])


def test_a_membership_reads_the_same_in_the_welcome_mail_and_on_the_card(client, db_session, sent):
    from fastapi import BackgroundTasks

    from app.domains.membership.api import FamilyCreate, register_family
    from tests.conftest import seed_postal_code

    email = "lidmaatschap-1775@example.com"
    seed_postal_code(db_session)
    db_session.commit()
    form = FamilyCreate.model_validate(
        {
            "street": "Voorbeeldstraat",
            "house_number": "7",
            "postal_code": "2400",
            "payment_method": "transfer",
            "members": [
                {
                    "last_name": "Proef",
                    "first_name": "Lid",
                    "email": email,
                    "mobile": "0470123456",
                    "date_of_birth": "1980-01-01",
                    "gender_code": "F",
                    "relation_type": "HOOFDLID",
                }
            ],
        }
    )
    register_family(db_session, form, BackgroundTasks(), signed_in=None)
    _run_queue(db_session)
    mail = _mail_lines(next(m["body"] for m in sent if m["type"] == "membership_confirmation"))

    _sign_in(client, email)
    card = client.get("/leden/gezin").text
    screen = _screen_lines(card[card.index("data-membership-status") :])

    assert [label for label, _value in mail] == LABELS
    assert mail == screen
    assert dict(mail)["IBAN"] == IBAN and dict(mail)["Begunstigde"] == HOLDER


def test_the_day_to_pay_before_is_the_bookings_own_day_plus_the_term(db_session, monkeypatch):
    """Not today plus the term: the mail is read on the day it is sent, the screen
    whenever — and both must name the same day."""
    from decimal import Decimal

    from app.config import settings
    from app.domains.payment.api import create_payment_record

    monkeypatch.setattr(settings, "payment_term_days", 14)
    record = create_payment_record(db_session, "membership", 1, Decimal("35.00"), "transfer")
    record.created_at = datetime(2031, 3, 1, 23, 30, tzinfo=timezone.utc)  # 2 March in Belgium
    db_session.flush()

    due = transfer_due(db_session, db_session.get(PaymentRecord, record.id), "x")

    assert due.pay_before == datetime(2031, 3, 2).date() + timedelta(days=14)
    assert due.lines[-1].label == "Te betalen vóór" and due.lines[-1].value == "16/03/2031"
    assert [line.label for line in due.lines] == LABELS
    assert [line.to_copy for line in due.lines] == [True, True, False, True, False]
