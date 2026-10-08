"""CR-13 phase 4, B8 test 12: the two registration mails say what they said.

Phase 4 turns the two direct mail calls of the registration doors into events —
`RegistrationConfirmed`, `FamilyRegistered` — whose handler builds the message in
the request and queues it as a job. The message must not change (R13), so both are
captured at `_send`, the last step before SMTP, on the code **before** the change
(master `6f9b37d0`), kept, and the new code must send the same — after its queue
has run (`run_due_jobs`; the scheduler is off in the tests).

**The family welcome has no "before" on master:** it has not been sent since v2.7.0,
because `escape` failed on the `RelationType` member the form carries since CR-12
phase 2 (found here, repaired in this phase). Its snapshot is recorded after the
repair, and the builder was compared line by line with the function of v2.6.0 — the
last release that sent it: identical but for `.value` on the relation type.

Dates depend on the day the test runs and the structured communication on the ids
a run hands out; both are masked, the rest is compared as sent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests._snapshot import compare, normalise
from tests.conftest import seed_activity_with_product, seed_postal_code, sign_up_at_the_door

pytestmark = pytest.mark.ui_agnostisch

SNAPSHOTS = Path(__file__).parent / "snapshots" / "registration_mail"
BEFORE = "the mails became events (CR-13 phase 4)"

MASKS = (
    (re.compile(r"\+\+\+\d{3}/\d{4}/\d{5}\+\+\+"), "<OGM>"),
    (re.compile(r"\b\d{2}/\d{2}/\d{4}\b"), "<DATE>"),
    (re.compile(r"\b\d{2}-\d{2}-\d{4}\b"), "<DATE>"),
)


@pytest.fixture
def sent(monkeypatch):
    from app.domains.mail import service

    captured: list[dict] = []

    def _capture(to_email, subject, body_html, cc=None, email_type="other"):
        captured.append(
            {"to": to_email, "subject": subject, "body": body_html, "cc": cc, "type": email_type}
        )

    monkeypatch.setattr(service, "_send", _capture)
    return captured


def _run_queue(db) -> None:
    """Whatever the code under test queued; on the old code there is nothing."""
    from app.kernel.jobs import run_due_jobs

    run_due_jobs(db)


def _rendered(mails: list[dict]) -> str:
    parts = []
    for mail in mails:
        text = f"to: {mail['to']}\ncc: {mail['cc']}\ntype: {mail['type']}\nsubject: {mail['subject']}\n{mail['body']}"
        for pattern, name in MASKS:
            text = pattern.sub(name, text)
        parts.append(normalise(text, {}, {}))
    return "\n=====\n".join(parts)


def test_the_activity_confirmation(client, db_session, sent):
    activity, component, product = seed_activity_with_product(db_session, price="12.50")
    db_session.commit()
    response = client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            "contact_name": "Mail Proef",
            "contact_email": "mail-proef@example.com",
            "phone": "0470000000",
            f"product_{product.id}": "2",
            "payment_method": "transfer",
        },
    )
    assert response.status_code == 200, response.text[:300]
    _run_queue(db_session)
    confirmations = [m for m in sent if m["type"] == "activity_confirmation"]
    assert len(confirmations) == 1, [m["subject"] for m in sent]
    compare(SNAPSHOTS, "activity", _rendered(confirmations), BEFORE)


def test_the_family_welcome(client, db_session, sent):
    seed_postal_code(db_session)
    db_session.commit()
    response = sign_up_at_the_door(
        client,
        json={
            "street": "Mailstraat",
            "house_number": "7",
            "bus_number": "b",
            "postal_code": "2400",
            "payment_method": "transfer",
            "members": [
                {
                    "last_name": "Proef",
                    "first_name": "Welkom",
                    "email": "welkom-proef@example.com",
                    "mobile": "0470123456",
                    "date_of_birth": "1980-01-01",
                    "gender_code": "F",
                    "relation_type": "HOOFDLID",
                },
                {
                    "last_name": "Proef",
                    "first_name": "Kind",
                    "date_of_birth": "2012-05-06",
                    "gender_code": "M",
                    "relation_type": "KIND",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text[:300]
    _run_queue(db_session)
    welcomes = [m for m in sent if m["type"] == "membership_confirmation"]
    assert len(welcomes) == 1, [m["subject"] for m in sent]
    compare(SNAPSHOTS, "family", _rendered(welcomes), BEFORE)
