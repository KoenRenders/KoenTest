"""#1297 — every public way in drops what is not a person, and lets a person through.

Measured on PROD: 25 automated submissions to the contact form in three days, each
opening a task for the board, all under the per-IP limit. The guard
(`app/kernel/form_guard.py`) sits in the services, so these tests walk every way in
and check both directions:

- **dropped** — honeypot filled, no signed time, or one too fresh: the visitor sees
  the ordinary thanks, and there is no row, no task, no mail. A log line names the
  reason and never the content;
- **let through** — the same form with a person's fields stores as before.

The ways in: `/berichten`, `/formulier/{token}` and `/nieuwsbrief`. A fourth, the
JSON route `/api/v1/forms/by-token/{token}/submit`, had no caller and went with
CR-13 phase 4b (#1251); it built the same proof and called the same function as
the public form, whose tests stand below.

Proven red (29 September 2026), both directions, additively:
- `return None` added at the top of `form_guard.refusal` (the guard off) → every
  "dropped" test fails on a row or a task that should not be there;
- `MIN_SECONDS = 60` added (the guard too strict) → every "let through" test fails
  on a missing row: that is the silent refusal of a person the issue warns of.
"""

import logging

import pytest

from app.domains.forms.models import Form, FormField, FormSubmission
from app.domains.newsletter.models import Subscriber
from app.domains.workflow.models import WorkflowTask
from app.kernel.form_guard import issue_token
from tests.conftest import form_guard_fields

pytestmark = pytest.mark.ui_serverrendered

TOKEN = "tok-guard-1297"


def _dropped_variants():
    return {
        "honeypot": {**form_guard_fields(), "website": "http://spam.example"},
        "no-token": {"website": ""},
        "too-fresh": {"website": "", "form_ts": issue_token()},
    }


VARIANTS = ["honeypot", "no-token", "too-fresh"]
REASON = {"honeypot": "honeypot", "no-token": "no_token", "too-fresh": "too_fast"}


@pytest.fixture
def public_form(db_session):
    form = Form(title="Inschrijving buurtfeest", share_token=TOKEN, status="open")
    db_session.add(form)
    db_session.flush()
    field = FormField(form_id=form.id, field_type="text", label="Opmerking", position=0)
    db_session.add(field)
    db_session.flush()
    return form, field


@pytest.fixture
def confirmations(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.domains.mail.api.send_newsletter_confirmation",
        lambda to, name, url: sent.append(to) or "sent",
    )
    return sent


def _counts(db):
    return (
        db.query(FormSubmission).count(),
        db.query(WorkflowTask).count(),
        db.query(Subscriber).count(),
    )


# ── /berichten ────────────────────────────────────────────────────────────────

BERICHT = {"naam": "Abcdefghij", "email": "probe@example.com", "bericht": "x" * 30}


@pytest.mark.parametrize("variant", VARIANTS)
def test_berichten_drops_what_is_not_a_person(client, db_session, caplog, variant):
    caplog.set_level(logging.WARNING, logger="app.kernel.form_guard")
    before = _counts(db_session)

    answer = client.post("/berichten", data={**_dropped_variants()[variant], **BERICHT})

    assert answer.headers.get("HX-Redirect") == "/?bericht=verzonden", "not the ordinary thanks"
    assert _counts(db_session) == before, "a dropped message left a row or a task"
    line = caplog.records[-1].getMessage()
    assert "berichten" in line and REASON[variant] in line, line
    assert "x" * 30 not in line and "probe@example.com" not in line, line


def test_berichten_lets_a_person_through(client, db_session):
    before = _counts(db_session)

    answer = client.post("/berichten", data={**form_guard_fields(), **BERICHT})

    assert answer.headers.get("HX-Redirect") == "/?bericht=verzonden"
    rows, tasks, _ = _counts(db_session)
    assert (rows, tasks) == (before[0] + 1, before[1] + 1), "a person's message was dropped"


# ── /formulier/{token} ────────────────────────────────────────────────────────


def _answer(field):
    return {"submitter_name": "Jo", "submitter_email": "jo@example.com", f"f{field.id}": "ok"}


@pytest.mark.parametrize("variant", VARIANTS)
def test_the_public_form_drops_what_is_not_a_person(client, db_session, public_form, variant):
    form, field = public_form

    answer = client.post(
        f"/formulier/{TOKEN}", data={**_dropped_variants()[variant], **_answer(field)}
    )

    assert answer.status_code == 200 and "Bedankt" in answer.text, "not the ordinary thanks"
    assert db_session.query(FormSubmission).filter_by(form_id=form.id).count() == 0


def test_the_public_form_lets_a_person_through(client, db_session, public_form):
    form, field = public_form

    answer = client.post(f"/formulier/{TOKEN}", data={**form_guard_fields(), **_answer(field)})

    assert "Bedankt" in answer.text
    assert db_session.query(FormSubmission).filter_by(form_id=form.id).count() == 1


# ── /nieuwsbrief ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("variant", VARIANTS)
def test_the_newsletter_drops_what_is_not_a_person(client, db_session, confirmations, variant):
    answer = client.post(
        "/nieuwsbrief", data={**_dropped_variants()[variant], "email": "probe@example.org"}
    )

    assert "Kijk in je mailbox" in answer.text, "not the ordinary answer"
    assert db_session.query(Subscriber).count() == 0 and confirmations == []


def test_the_newsletter_lets_a_person_through(client, db_session, confirmations):
    answer = client.post("/nieuwsbrief", data={**form_guard_fields(), "email": "an@example.org"})

    assert "Kijk in je mailbox" in answer.text
    assert db_session.query(Subscriber).count() == 1 and confirmations == ["an@example.org"]
