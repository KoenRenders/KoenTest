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

#1839 — the "too fresh" case holds the guard's clock. It issued a token and
posted at once, on the wall clock, and went red once on CI: the guard counts
from a floored second, so a token issued late in a second is two seconds old
about one second later, and a slow first request was enough. With the clock
held the token is younger than a second whatever the request takes. Where the
line of two seconds lies exactly is pinned in `tests/test_form_guard_rules.py`.
Proven, with a slow request simulated by a sleep of 1.2 s at the top of the
guard's check (additive, put back): with the clock held the three "too-fresh"
cases stay green; with the fixture's clock let go and the token issued at x.9
of a second, all three are red — the failure of CI, made certain.
"""

import logging
import time
from types import SimpleNamespace

import pytest

from app.domains.forms.models import Form, FormField, FormSubmission
from app.domains.newsletter.models import Subscriber
from app.domains.workflow.models import WorkflowTask
from app.kernel import form_guard
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


@pytest.fixture
def held_clock(monkeypatch):
    """The guard's clock stands still at this moment (#1839): a token issued
    under it is less than a second old when the guard reads it, however long
    the request takes. Only the guard's clock — the rest of the application
    keeps the real one."""
    moment = time.time()
    monkeypatch.setattr(form_guard, "time", SimpleNamespace(time=lambda: moment))


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


def _guard_line(caplog) -> str:
    """The last line the form guard itself logged."""
    lines = [r.getMessage() for r in caplog.records if r.name == "app.kernel.form_guard"]
    assert lines, "the form guard logged nothing"
    return lines[-1]


# ── /berichten ────────────────────────────────────────────────────────────────

BERICHT = {"naam": "Abcdefghij", "email": "probe@example.com", "bericht": "x" * 30}


@pytest.mark.parametrize("variant", VARIANTS)
def test_berichten_drops_what_is_not_a_person(client, db_session, caplog, held_clock, variant):
    caplog.set_level(logging.WARNING, logger="app.kernel.form_guard")
    before = _counts(db_session)

    answer = client.post("/berichten", data={**_dropped_variants()[variant], **BERICHT})

    assert answer.headers.get("HX-Redirect") == "/?bericht=verzonden", "not the ordinary thanks"
    assert _counts(db_session) == before, "a dropped message left a row or a task"
    # The guard's own line, not whatever was logged last (#1777): a request slower
    # than `slow_request_ms` gets a WARNING of its own after the guard's.
    line = _guard_line(caplog)
    assert "berichten" in line and REASON[variant] in line, line
    assert "x" * 30 not in line and "probe@example.com" not in line, line


def test_the_reason_is_read_from_the_guards_line_also_when_the_request_is_slow(
    client, db_session, caplog, monkeypatch
):
    """#1777: on a loaded runner the request took 685 ms, the application logged
    its slow-request WARNING after the guard's line, and the test above read
    that one — "POST /berichten -> 200 (684.8 ms)" — for the reason.

    Here every request is slow, so the slow-request line is always the last.
    Red every time on the old reading (`caplog.records[-1]`), proven on
    8 October 2026 by putting that line back in `_guard_line`.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "slow_request_ms", -1)
    caplog.set_level(logging.WARNING, logger="app.kernel.form_guard")

    client.post("/berichten", data={**_dropped_variants()["no-token"], **BERICHT})

    assert "POST /berichten" in caplog.records[-1].getMessage(), "no slow-request line"
    assert REASON["no-token"] in _guard_line(caplog)


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
def test_the_public_form_drops_what_is_not_a_person(
    client, db_session, public_form, held_clock, variant
):
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
def test_the_newsletter_drops_what_is_not_a_person(
    client, db_session, confirmations, held_clock, variant
):
    answer = client.post(
        "/nieuwsbrief", data={**_dropped_variants()[variant], "email": "probe@example.org"}
    )

    assert "Kijk in je mailbox" in answer.text, "not the ordinary answer"
    assert db_session.query(Subscriber).count() == 0 and confirmations == []


def test_the_newsletter_lets_a_person_through(client, db_session, confirmations):
    answer = client.post("/nieuwsbrief", data={**form_guard_fields(), "email": "an@example.org"})

    assert "Kijk in je mailbox" in answer.text
    assert db_session.query(Subscriber).count() == 1 and confirmations == ["an@example.org"]
