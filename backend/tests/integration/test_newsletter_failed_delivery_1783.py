"""#1783 — a failed newsletter delivery says the true reason, is retried once and
can be sent again.

On 8 October 2026 two of 195 deliveries failed on "[Errno 101] Network is
unreachable"; the page said "de mailserver weigerde deze mail" for both, nothing
was tried again, and there was no way to send to them again.

- the mail service names the KIND of fault (`SendOutcome`, `fault_of`), and the
  newsletter writes a reason a board member can act on — it never reads the
  technical message;
- a temporary fault gets one more try within the same send, of a mail that is
  known not to have left; a permanent refusal gets none;
- "Opnieuw versturen" queues exactly the failed deliveries of a letter again.

Red (each restored after): the retry loop reduced to one try → the network fault
stays failed and one mail is attempted; the retry also for a permanent refusal →
two attempts where one is asked; `resend_failed` queuing every delivery → the
address that already got the letter gets it twice.
"""

from __future__ import annotations

import smtplib

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mail.api import SendOutcome
from app.domains.mail.service import fault_of
from app.domains.newsletter import service as nb
from app.domains.newsletter.api import Audience
from app.domains.newsletter.models import (
    Delivery,
    DeliveryKind,
    DeliveryStatus,
    LetterStatus,
    Newsletter,
)
from tests._letter import letter_doc
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

UNREACHABLE = "mailserver niet bereikbaar (tijdelijk)"
REFUSED = "adres geweigerd door de mailserver"
FOR_NOW = "tijdelijk geweigerd door de mailserver"


class _Mailbox:
    """The mail service's campaign send, answering per address from a script."""

    def __init__(self):
        self.script: dict[str, list[str]] = {}
        self.attempts: list[str] = []

    def __call__(self, to_email, subject, body_html, **kwargs):
        self.attempts.append(to_email)
        answers = self.script.get(to_email, [])
        return answers.pop(0) if answers else SendOutcome.SENT


@pytest.fixture
def mailbox(monkeypatch):
    box = _Mailbox()
    monkeypatch.setattr("app.domains.mail.api.send_campaign_mail", box)
    waits: list[int] = []
    monkeypatch.setattr(nb, "_wait_before_retry", lambda: waits.append(1))
    box.waits = waits
    return box


def _letter(db, *addresses, status=LetterStatus.SENDING, done=()):
    letter = Newsletter(
        subject="Proef",
        body_document=letter_doc("<div>Beste</div>"),
        audience=Audience.MEMBERS,
        status=status,
        sent_body_html="<div>Beste</div>",
    )
    db.add(letter)
    db.flush()
    for address in addresses:
        db.add(
            Delivery(
                newsletter_id=letter.id,
                email=address,
                kind=DeliveryKind.MEMBER,
                status=DeliveryStatus.SENT if address in done else DeliveryStatus.QUEUED,
            )
        )
    db.commit()
    return letter


def _by_address(db, letter) -> dict[str, Delivery]:
    db.expire_all()
    return {d.email: d for d in db.query(Delivery).filter_by(newsletter_id=letter.id)}


# ── The kind of fault ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (OSError(101, "Network is unreachable"), SendOutcome.UNREACHABLE),
        (TimeoutError("timed out"), SendOutcome.UNREACHABLE),
        (smtplib.SMTPServerDisconnected("Connection unexpectedly closed"), SendOutcome.UNREACHABLE),
        (smtplib.SMTPConnectError(421, b"try again"), SendOutcome.UNREACHABLE),
        (
            smtplib.SMTPRecipientsRefused({"x@example.com": (550, b"no such user")}),
            SendOutcome.REFUSED,
        ),
        (
            smtplib.SMTPRecipientsRefused({"x@example.com": (450, b"mailbox busy")}),
            SendOutcome.REFUSED_FOR_NOW,
        ),
        (smtplib.SMTPDataError(552, b"message refused"), SendOutcome.REFUSED),
        (smtplib.SMTPDataError(451, b"try later"), SendOutcome.REFUSED_FOR_NOW),
        (smtplib.SMTPAuthenticationError(535, b"bad credentials"), SendOutcome.FAILED),
        (ValueError("something else"), SendOutcome.FAILED),
    ],
)
def test_the_mail_service_names_the_kind_of_fault(exc, kind):
    assert fault_of(exc) == kind


def test_the_reason_is_the_kinds_own_sentence():
    assert nb.failure_reason(SendOutcome.UNREACHABLE) == UNREACHABLE
    assert nb.failure_reason(SendOutcome.REFUSED) == REFUSED
    assert nb.failure_reason(SendOutcome.REFUSED_FOR_NOW) == FOR_NOW
    assert nb.failure_reason(SendOutcome.FAILED) == "het versturen is mislukt"
    assert nb.failure_reason(SendOutcome.SKIPPED) == "geen mailaccount ingesteld"


# ── One retry, within the same send ──────────────────────────────────────────


def test_a_network_fault_is_tried_once_more_and_the_mail_leaves_once(db_session, mailbox):
    letter = _letter(db_session, "netwerk@example.com", "gewoon@example.com")
    mailbox.script["netwerk@example.com"] = [SendOutcome.UNREACHABLE, SendOutcome.SENT]

    assert nb.send_batch(db_session, letter.id) == "done"

    rows = _by_address(db_session, letter)
    assert rows["netwerk@example.com"].status == DeliveryStatus.SENT
    assert rows["netwerk@example.com"].error is None
    assert mailbox.attempts == ["netwerk@example.com", "netwerk@example.com", "gewoon@example.com"]
    assert len(mailbox.waits) == 1, "the retry comes after a pause"


def test_a_fault_that_stays_is_failed_with_the_true_reason_after_two_tries(db_session, mailbox):
    letter = _letter(db_session, "netwerk@example.com")
    mailbox.script["netwerk@example.com"] = [SendOutcome.UNREACHABLE, SendOutcome.UNREACHABLE]

    nb.send_batch(db_session, letter.id)

    row = _by_address(db_session, letter)["netwerk@example.com"]
    assert (row.status, row.error) == (DeliveryStatus.FAILED, UNREACHABLE)
    assert mailbox.attempts == ["netwerk@example.com"] * 2, "one retry, not more"


def test_a_permanent_refusal_is_not_tried_again(db_session, mailbox):
    letter = _letter(db_session, "fout@example.com")
    mailbox.script["fout@example.com"] = [SendOutcome.REFUSED, SendOutcome.SENT]

    nb.send_batch(db_session, letter.id)

    row = _by_address(db_session, letter)["fout@example.com"]
    assert (row.status, row.error) == (DeliveryStatus.FAILED, REFUSED)
    assert mailbox.attempts == ["fout@example.com"] and mailbox.waits == []


def test_a_temporary_refusal_is_tried_again_too(db_session, mailbox):
    letter = _letter(db_session, "druk@example.com")
    mailbox.script["druk@example.com"] = [SendOutcome.REFUSED_FOR_NOW, SendOutcome.REFUSED_FOR_NOW]

    nb.send_batch(db_session, letter.id)

    row = _by_address(db_session, letter)["druk@example.com"]
    assert (row.status, row.error) == (DeliveryStatus.FAILED, FOR_NOW)
    assert len(mailbox.attempts) == 2


# ── Opnieuw versturen ────────────────────────────────────────────────────────


def _failed_letter(db):
    letter = _letter(
        db,
        "aangekomen@example.com",
        "netwerk@example.com",
        "fout@example.com",
        status=LetterStatus.SENT,
        done=("aangekomen@example.com",),
    )
    for address, reason in (("netwerk@example.com", UNREACHABLE), ("fout@example.com", REFUSED)):
        row = db.query(Delivery).filter_by(newsletter_id=letter.id, email=address).one()
        row.status, row.error = DeliveryStatus.FAILED, reason
    db.commit()
    return letter


def test_sending_again_takes_only_the_failed_deliveries(db_session, mailbox):
    letter = _failed_letter(db_session)

    assert nb.resend_failed(db_session, letter) == 2
    assert letter.status == LetterStatus.SENDING
    assert nb.send_batch(db_session, letter.id) == "done"

    rows = _by_address(db_session, letter)
    assert sorted(mailbox.attempts) == ["fout@example.com", "netwerk@example.com"]
    assert "aangekomen@example.com" not in mailbox.attempts, "a sent delivery is never sent twice"
    assert {d.status for d in rows.values()} == {DeliveryStatus.SENT}
    assert db_session.get(Newsletter, letter.id).status == LetterStatus.SENT


def test_sending_again_without_a_failed_delivery_is_refused(db_session, mailbox):
    letter = _letter(
        db_session,
        "aangekomen@example.com",
        status=LetterStatus.SENT,
        done=("aangekomen@example.com",),
    )

    with pytest.raises(nb.NewsletterError, match="geen mislukte adressen"):
        nb.resend_failed(db_session, letter)
    assert mailbox.attempts == []


def test_the_page_offers_it_with_the_number_and_says_what_it_did(client, db_session, mailbox):
    letter = _failed_letter(db_session)
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)

    page = client.get(f"/admin/nieuwsbrieven/{letter.id}").text
    assert page.count("data-resend-failed") == 1
    assert 'data-confirm="De nieuwsbrief opnieuw sturen naar 2 mislukte adressen?"' in page
    assert "Opnieuw versturen naar 2 mislukte adressen" in page, "the button names its audience"
    assert UNREACHABLE in page and REFUSED in page

    answer = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/opnieuw",
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    assert answer.status_code == 204
    assert answer.headers["HX-Redirect"] == f"/admin/nieuwsbrieven/{letter.id}?opnieuw=2"
    after = client.get(answer.headers["HX-Redirect"]).text
    assert "2 mislukte adressen staan opnieuw in de wachtrij." in after
    assert "data-resend-failed" not in after, "nothing is failed any more"


def test_a_letter_without_failed_deliveries_shows_no_button(client, db_session, mailbox):
    letter = _letter(
        db_session,
        "aangekomen@example.com",
        status=LetterStatus.SENT,
        done=("aangekomen@example.com",),
    )
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    assert "data-resend-failed" not in client.get(f"/admin/nieuwsbrieven/{letter.id}").text


# ── Bounced by hand (#2188) ──────────────────────────────────────────────────
#
# Broken to prove them: `resend_failed` taking only `FAILED` (the bounced one then
# stays put), `mark_bounced` accepting any status, and the row menu offering the
# action on every status.

BOUNCED = "teruggekomen@example.com"
ARRIVED = "aangekomen@example.com"


def _sent_letter(db):
    return _letter(db, ARRIVED, BOUNCED, status=LetterStatus.SENT, done=(ARRIVED, BOUNCED))


def _id_of(db, letter, address):
    return db.query(Delivery).filter_by(newsletter_id=letter.id, email=address).one().id


def test_a_marked_delivery_is_sent_again_and_an_unmarked_one_is_not(db_session, mailbox):
    letter = _sent_letter(db_session)
    nb.mark_bounced(db_session, letter, _id_of(db_session, letter, BOUNCED))

    assert nb.progress_of(db_session, letter).to_resend == 1
    assert nb.resend_failed(db_session, letter) == 1
    assert nb.send_batch(db_session, letter.id) == "done"

    assert mailbox.attempts == [BOUNCED], "the one that arrived is never sent twice"
    rows = _by_address(db_session, letter)
    assert rows[BOUNCED].status == DeliveryStatus.SENT
    assert rows[BOUNCED].email == BOUNCED, "the stored address is used"


def test_failed_and_bounced_are_sent_again_together(db_session, mailbox):
    letter = _letter(
        db_session, ARRIVED, BOUNCED, "fout@example.com",
        status=LetterStatus.SENT, done=(ARRIVED, BOUNCED),
    )  # fmt: skip
    nb.mark_bounced(db_session, letter, _id_of(db_session, letter, BOUNCED))
    failed = db_session.query(Delivery).filter_by(email="fout@example.com").one()
    failed.status = DeliveryStatus.FAILED
    db_session.commit()

    assert nb.progress_of(db_session, letter).to_resend == 2
    assert nb.resend_failed(db_session, letter) == 2


def test_taking_the_mark_back_puts_it_on_sent_and_it_is_not_sent_again(db_session, mailbox):
    letter = _sent_letter(db_session)
    delivery_id = _id_of(db_session, letter, BOUNCED)
    nb.mark_bounced(db_session, letter, delivery_id)
    nb.unmark_bounced(db_session, letter, delivery_id)

    assert _by_address(db_session, letter)[BOUNCED].status == DeliveryStatus.SENT
    with pytest.raises(nb.NewsletterError, match="geen mislukte adressen"):
        nb.resend_failed(db_session, letter)


def test_only_a_sent_delivery_can_be_marked_and_only_a_marked_one_taken_back(db_session):
    letter = _letter(db_session, ARRIVED, BOUNCED, status=LetterStatus.SENT, done=(BOUNCED,))
    queued = _id_of(db_session, letter, ARRIVED)

    with pytest.raises(nb.NewsletterError, match="verstuurde"):
        nb.mark_bounced(db_session, letter, queued)
    with pytest.raises(nb.NewsletterError, match="niet als teruggekomen"):
        nb.unmark_bounced(db_session, letter, _id_of(db_session, letter, BOUNCED))


def test_the_row_menu_and_the_button_follow_the_status(client, db_session, mailbox):
    letter = _sent_letter(db_session)
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    headers = {"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"}
    base = f"/admin/nieuwsbrieven/{letter.id}"

    page = client.get(base).text
    assert page.count("Teruggekomen</button>") == 2, "each sent row offers it"
    assert "data-resend-failed" not in page

    answer = client.post(
        f"{base}/afleveringen/{_id_of(db_session, letter, BOUNCED)}/teruggekomen",
        headers=headers,
    )
    assert answer.headers["HX-Redirect"] == base
    page = client.get(base).text
    assert "Opnieuw versturen naar 1 mislukt adres" in page, "the label is the same"
    assert "Toch aangekomen</button>" in page and page.count("Teruggekomen</button>") == 1

    answer = client.post(
        f"{base}/afleveringen/{_id_of(db_session, letter, BOUNCED)}/terugzetten",
        headers=headers,
    )
    assert answer.headers["HX-Redirect"] == base
    assert "data-resend-failed" not in client.get(base).text


def test_a_delivery_of_another_letter_cannot_be_marked(db_session):
    letter = _sent_letter(db_session)
    other = _letter(
        db_session, "ander@example.com", status=LetterStatus.SENT, done=("ander@example.com",)
    )
    with pytest.raises(nb.NewsletterError, match="hoort niet bij"):
        nb.mark_bounced(db_session, letter, _id_of(db_session, other, "ander@example.com"))
