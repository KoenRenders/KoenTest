"""The sign-in asks `mail` for its mail and no longer sends it (CR-13 phase 4d, #1251).

`start_login` called `mail.api.send_magic_link` and
`send_member_contact_board_notice` itself, after its commit: the request waited
for the mail server, and the mail was no part of the transaction that stored the
code. It now publishes `CodeMailRequested` — kind `SIGN_IN`, or
`AMBIGUOUS_ADDRESS` for an address that does not say who signs in — and `mail`
queues the message in that same transaction.

Proven red, each by one edit that was put back:

- the `_request_mail(db, email, SIGN_IN, …)` line taken out of `start_login` →
  the first test fails on an empty queue, the fourth on "DID NOT RAISE";
- the `SIGN_IN` branch of `mail.handlers.queue_code_mail` made unreachable → the
  first and the fourth test fail on "Unknown kind of code mail: sign_in";
- `_request_mail(db, email, AMBIGUOUS_ADDRESS)` taken out → the second test
  fails on an empty queue;
- the `db.commit()` moved back above the request for the mail → the fourth test
  fails: the code is stored although its mail could not be built.
"""

from datetime import date

import pytest

from app.domains.auth import login as auth_login
from app.domains.auth.api import LoginToken, start_login
from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person, new_contact_detail
from app.kernel.jobs import run_due_jobs
from tests._queued_mail import queued_link, queued_mails

CODE = "313131"
KNOWN = "bekend@example.com"
SHARED = "tweegezinnen@example.com"


@pytest.fixture(autouse=True)
def a_known_code(monkeypatch):
    monkeypatch.setattr(auth_login, "_generate_otp", lambda: CODE)


@pytest.fixture
def sent(monkeypatch):
    """What reaches the sender — the one function behind which the network lies."""
    from app.domains.mail import service

    captured: list[dict] = []

    def _capture(to_email, subject, body_html, cc=None, email_type="other"):
        captured.append({"to": to_email, "subject": subject, "body": body_html, "type": email_type})

    monkeypatch.setattr(service, "_send", _capture)
    return captured


def _person(db, first_name, *, household=False):
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name=first_name, last_name="Proef"
    )
    db.add(person)
    db.flush()
    if household:
        member = Member()
        db.add(member)
        db.flush()
        db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type="HOOFDLID"))
        db.flush()
    return person


def test_the_sign_in_mail_waits_in_the_queue_and_is_sent_by_the_job(db_session, sent):
    person = _person(db_session, "Bekend")
    db_session.add(new_contact_detail(db_session, person, "EMAIL", KNOWN, is_primary=True))
    db_session.commit()

    start_login(db_session, KNOWN, return_to="/leden/gezin")

    assert sent == [], "the request itself reaches no mail server"
    (mail,) = queued_mails(db_session, KNOWN)
    assert mail["email_type"] == "magic_link"
    assert mail["subject"].startswith("Inloglink ")
    assert CODE in mail["body_html"], "the code for whoever signs in on another device"
    link = queued_link(db_session, KNOWN)
    assert "/login/verify?token=" in link and "terug=/leden/gezin" in link
    token = db_session.query(LoginToken).filter_by(email=KNOWN).one()
    assert token.token in link, "the link carries the token stored beside it"

    run_due_jobs(db_session)
    assert [(m["to"], m["type"]) for m in sent] == [(KNOWN, "magic_link")]
    assert sent[0]["body"] == mail["body_html"]


def test_an_address_of_two_households_gets_the_board_notice_through_the_queue(db_session, sent):
    """Made without the factory, as old rows were: master data refuses a second
    owner today."""
    for name in ("Een", "Twee"):
        person = _person(db_session, name, household=True)
        db_session.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=SHARED))
    db_session.commit()

    start_login(db_session, SHARED)

    assert sent == []
    (mail,) = queued_mails(db_session, SHARED)
    assert mail["email_type"] == "member_contact_notice"
    assert "href=" not in mail["body_html"], "no link: we do not guess which household"
    assert db_session.query(LoginToken).filter_by(email=SHARED).count() == 0


def test_an_unknown_address_queues_nothing(db_session, sent):
    start_login(db_session, "niemand@example.com")

    assert queued_mails(db_session, "niemand@example.com") == []
    assert db_session.query(LoginToken).filter_by(email="niemand@example.com").count() == 0


def test_a_mail_that_cannot_be_built_stores_no_code(db_session, monkeypatch):
    """The one difference in what a visitor can meet: the mail is worded inside
    the request's transaction, so a mail that cannot be built stops the request
    and leaves no code behind — before, the code was committed first and the
    failure came after it."""
    from app.domains.mail import service

    person = _person(db_session, "Bekend")
    db_session.add(new_contact_detail(db_session, person, "EMAIL", KNOWN, is_primary=True))
    db_session.commit()

    def _broken(link, otp_code=None):
        raise RuntimeError("the mail cannot be built")

    monkeypatch.setattr(service, "sign_in_message", _broken)
    with pytest.raises(RuntimeError, match="cannot be built"):
        start_login(db_session, KNOWN)
    db_session.rollback()

    assert db_session.query(LoginToken).filter_by(email=KNOWN).count() == 0
    assert queued_mails(db_session, KNOWN) == []
