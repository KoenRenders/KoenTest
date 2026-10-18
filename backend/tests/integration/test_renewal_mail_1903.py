"""#1903 — a membership renewal sends a confirmation mail, and the same one when the
board renews.

The rule (Koen, 11 October 2026): every order results in a mail to the one who
ordered, and the same mail goes out when the board places it. The renewal was
the one order that sent nothing.

Membership publishes `MembershipRenewalPlaced` in the renewal's transaction;
mail words the message and queues it, so it leaves after the commit. It goes to
the household's MAIN MEMBER, at his confirmed address — whoever placed the
renewal. What is held here, read from the QUEUE (the job that sends), not from
the template:

- a transfer from the public side queues one mail to the main member with the
  amount and the structured communication of the booking that was made;
- the same from the back office: the same mail, to the main member and not to
  the board member who clicked;
- a partner who renews: the mail still goes to the main member;
- online: one mail, without a transfer block, saying when the membership
  becomes active;
- a refused renewal queues nothing;
- a main member without a confirmed address: no mail, the renewal stands, and
  the board's record says so — and does not say so when the address is there;
- the transfer block of this mail and of the registration mail are one source:
  the same labels in the same order, and one place in the mail domain that
  writes a transfer's lines.

Proven red (locally, restored), each by an addition:
- `addressee = None` under the line that reads the addressee → the five tests
  that expect a mail fail on "0 mails";
- the addressee replaced by `bestuur@example.org` under that same line → "the
  mail went to bestuur@example.org";
- `transfer = None` at the top of `membership_renewal_message` → "the mail of a
  transfer carries no transfer block";
- `or True` behind the record's condition for the line → "the record says the
  mail was not sent although it was".
"""

from __future__ import annotations

import re
from html import unescape

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import ContactDetail, MemberPerson, Person
from app.domains.membership.api import open_renewal_payment
from tests.conftest import SEEDED_ADMIN_EMAIL, board_session, create_test_family

pytestmark = pytest.mark.ui_serverrendered

LABELS = ["Bedrag", "IBAN", "Begunstigde", "Gestructureerde mededeling", "Te betalen vóór"]
UNMAILED = "data-renewal-unmailed"


@pytest.fixture(autouse=True)
def account(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "payment_iban", "BE00 0000 0000 0000")
    monkeypatch.setattr(settings, "payment_beneficiary", "Voorbeeldvereniging")


@pytest.fixture
def sent(monkeypatch):
    """What the send job hands to the one place that sends."""
    from app.domains.mail import service

    captured: list[dict] = []

    def _capture(to_email, subject, body_html, cc=None, email_type="other"):
        captured.append({"to": to_email, "subject": subject, "body": body_html, "type": email_type})

    monkeypatch.setattr(service, "_send", _capture)
    return captured


def _run_queue(db) -> None:
    from app.kernel.jobs import run_due_jobs

    run_due_jobs(db)


def _renewal_mails(db, sent) -> list[dict]:
    _run_queue(db)
    return [m for m in sent if m["type"] == "membership_confirmation"]


def _member_renews(client, email: str, method: str):
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return client.post(
        "/leden/gezin/vernieuwen",
        data={"payment_method": method},
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )


def _board_renews(client, household_id: int, method: str):
    return client.post(
        f"/admin/leden/gezin/{household_id}/vernieuwen",
        data={"payment_method": method},
        headers=board_session(client),
    )


def _transfer_lines(body: str) -> list[tuple[str, str]]:
    assert "Betaalinstructies (overschrijving)" in body, (
        "the mail of a transfer carries no transfer block"
    )
    block = body[body.index("Betaalinstructies (overschrijving)") :]
    block = block[: block.index("</ul>")]
    found = re.findall(r"<li><strong>([^<]+):</strong>\s*([^<]*)</li>", block)
    return [(unescape(label), unescape(value).strip()) for label, value in found]


def _one(mails: list[dict], to: str) -> dict:
    assert len(mails) == 1, f"{len(mails)} mails"
    assert mails[0]["to"] == to, f"the mail went to {mails[0]['to']}"
    return mails[0]


def test_a_transfer_from_the_public_side_mails_the_booking_that_was_made(client, db_session, sent):
    member, _person = create_test_family(db_session, email="lid-1903@example.com")
    db_session.commit()

    answer = _member_renews(client, "lid-1903@example.com", "transfer")

    assert answer.status_code == 200, answer.text[:300]
    mail = _one(_renewal_mails(db_session, sent), "lid-1903@example.com")
    booking = open_renewal_payment(db_session, member)
    lines = dict(_transfer_lines(mail["body"]))
    assert lines["Gestructureerde mededeling"] == booking.structured_communication
    assert lines["Bedrag"].startswith("€ ") and lines["Bedrag"] != "€ 0,00"
    assert "wordt actief zodra" not in mail["body"], "a transfer is told about an online payment"


def test_the_board_renews_and_the_main_member_gets_the_same_mail(client, db_session, sent):
    member, _person = create_test_family(db_session, email="hoofd-1903@example.com")
    other, _p = create_test_family(db_session, email="zelf-1903@example.com")
    db_session.commit()

    assert _board_renews(client, member.id, "transfer").status_code == 200
    by_the_board = _one(_renewal_mails(db_session, sent), "hoofd-1903@example.com")
    assert SEEDED_ADMIN_EMAIL not in by_the_board["body"]
    sent.clear()
    assert _member_renews(client, "zelf-1903@example.com", "transfer").status_code == 200
    by_the_member = _one(_renewal_mails(db_session, sent), "zelf-1903@example.com")

    def shape(mail: dict) -> tuple:
        lines = _transfer_lines(mail["body"])
        return mail["subject"], [label for label, _value in lines]

    assert shape(by_the_board) == shape(by_the_member), "the board's renewal mails something else"
    board_session(client)
    record = client.get(f"/admin/leden/gezin/{member.id}").text
    assert "data-renewal-running" in record
    assert UNMAILED not in record, "the record says the mail was not sent although it was"


def test_a_partner_who_renews_has_the_mail_sent_to_the_main_member(client, db_session, sent):
    member, _person = create_test_family(db_session, email="hoofdlid-p-1903@example.com")
    from datetime import date

    partner = Person(
        first_name="Paula", last_name="Partner", date_of_birth=date(1982, 5, 6), gender_code="F"
    )
    db_session.add(partner)
    db_session.flush()
    db_session.add(MemberPerson(member_id=member.id, person_id=partner.id, relation_type="PARTNER"))
    db_session.add(
        ContactDetail(
            person_id=partner.id,
            contact_type_code="EMAIL",
            value="partner-1903@example.com",
            is_primary=True,
        )
    )
    db_session.commit()

    assert _member_renews(client, "partner-1903@example.com", "transfer").status_code == 200

    _one(_renewal_mails(db_session, sent), "hoofdlid-p-1903@example.com")


def test_online_mails_once_and_says_when_it_becomes_active(client, db_session, sent, mock_mollie):
    create_test_family(db_session, email="online-1903@example.com")
    db_session.commit()

    assert _member_renews(client, "online-1903@example.com", "online").status_code == 200

    mail = _one(_renewal_mails(db_session, sent), "online-1903@example.com")
    assert "Het lidmaatschap wordt actief zodra we je betaling ontvangen hebben." in mail["body"]
    assert "Betaalinstructies" not in mail["body"]


def test_a_refused_renewal_mails_nothing(client, db_session, sent):
    create_test_family(db_session, email="tweemaal-1903@example.com")
    db_session.commit()
    assert _member_renews(client, "tweemaal-1903@example.com", "transfer").status_code == 200
    _renewal_mails(db_session, sent)
    sent.clear()

    again = _member_renews(client, "tweemaal-1903@example.com", "transfer")

    assert again.status_code == 422, "a second renewal was not refused — this proves nothing"
    assert _renewal_mails(db_session, sent) == []


def test_without_a_confirmed_address_nothing_is_mailed_and_the_record_says_so(
    client, db_session, sent
):
    member, person = create_test_family(db_session, email="wacht-1903@example.com")
    for detail in db_session.query(ContactDetail).filter_by(person_id=person.id):
        detail.confirmed_at = None
    db_session.commit()

    answer = _board_renews(client, member.id, "transfer")

    assert answer.status_code == 200, "the renewal itself must stand"
    assert open_renewal_payment(db_session, member) is not None
    assert _renewal_mails(db_session, sent) == []
    record = client.get(f"/admin/leden/gezin/{member.id}").text
    assert UNMAILED in record
    assert "de bevestiging van deze vernieuwing is niet gemaild" in record


def test_the_transfer_block_is_the_one_of_the_registration_mail(client, db_session, sent):
    """One source (#1775): the renewal mail's transfer block carries the labels of
    payment's `TransferDue`, in its order — and in the mail domain exactly one
    function writes a transfer's lines, which both confirmation mails call."""
    from pathlib import Path

    create_test_family(db_session, email="bron-1903@example.com")
    db_session.commit()
    assert _member_renews(client, "bron-1903@example.com", "transfer").status_code == 200
    mail = _one(_renewal_mails(db_session, sent), "bron-1903@example.com")

    assert [label for label, _value in _transfer_lines(mail["body"])] == LABELS

    source = (Path(__file__).resolve().parents[2] / "app/domains/mail/service.py").read_text()
    assert source.count("transfer.lines") == 1, "a second place writes a transfer's lines"
    # Its definition and one call per confirmation mail: the welcome, the
    # renewal, the registration and the order.
    assert source.count("_transfer_instructions_html(transfer)") == 5, (
        "the confirmation mails do not all call the one transfer block"
    )
    # "Bedrag" is a fact of the renewal too; the four others are the transfer's own.
    for label in LABELS[1:]:
        assert f'"{label}"' not in source, f"the mail domain words '{label}' itself"
