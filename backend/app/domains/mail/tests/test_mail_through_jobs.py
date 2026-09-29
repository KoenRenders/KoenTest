"""CR-13 phase 4 (#1251, §B4.1): a mail handler queues a job; the job sends.

What this changes, and what the tests below hold:

- **a rolled-back registration sends nothing** — the job row is written in the
  registration's transaction and goes with it;
- **a committed one sends exactly one mail**, when the queue runs;
- **the queued message is gone once sent** — `kernel_jobs` keeps no retention, the
  mail log does (#328), so the job empties its payload;
- **the scheduler is woken by the commit** that queued a job, so the mail leaves
  within a second and not at the next 30-second tick.

Broken on purpose to check these tests can go red (run, then restored), each
additively, with what failed:

- `queue = None` as the first line after `_dispatch`'s docstring (the old
  in-request path) → four: the rollback test (the mail left anyway), "nothing is
  sent inside the handler", the scrub test and the wake test (no job was queued);
- `_scrub_when_done.clear()` added in `run_due_jobs` before the scrub → the scrub
  test alone;
- `return` as the first line of `_wake_after_commit` → the wake test alone.
"""

from __future__ import annotations

import pytest

from app.domains.mail.service import SEND_JOB
from app.kernel import jobs
from app.kernel.contracts.mail import MailRequested
from app.kernel.events import publish

pytestmark = pytest.mark.ui_agnostisch


@pytest.fixture
def sent(monkeypatch):
    from app.domains.mail import service

    captured: list[str] = []
    monkeypatch.setattr(service, "_send", lambda to, *args, **kwargs: captured.append(to))
    return captured


def _request(to: str) -> MailRequested:
    return MailRequested(to_email=to, subject="Proef", body_html="<p>Proef</p>")


def test_a_rolled_back_transaction_sends_nothing(db_session, sent):
    savepoint = db_session.begin_nested()
    publish(_request("teruggedraaid@example.com"), db_session)
    savepoint.rollback()

    jobs.run_due_jobs(db_session)

    assert sent == [], "a mail left for a transaction that was rolled back"


def test_a_committed_one_sends_exactly_one(db_session, sent):
    publish(_request("bevestigd@example.com"), db_session)
    db_session.commit()

    jobs.run_due_jobs(db_session)
    jobs.run_due_jobs(db_session)

    assert sent == ["bevestigd@example.com"]


def test_nothing_is_sent_inside_the_handler(db_session, sent):
    """The handler queues; the network waits for the job (§B4.1)."""
    publish(_request("wacht@example.com"), db_session)
    assert sent == []


def test_the_sent_message_does_not_stay_in_the_queue(db_session, sent):
    publish(_request("gewist@example.com"), db_session)
    db_session.commit()
    jobs.run_due_jobs(db_session)

    job = (
        db_session.query(jobs.KernelJob)
        .filter(jobs.KernelJob.name == SEND_JOB)
        .order_by(jobs.KernelJob.id.desc())
        .first()
    )
    assert job.status is jobs.JobStatus.DONE
    assert job.payload == {}, "the message stayed in kernel_jobs after it was sent"


def test_the_commit_that_queued_a_job_wakes_the_scheduler(db_session, sent):
    jobs._wake.clear()
    db_session.commit()
    assert not jobs._wake.is_set(), "a commit without a job woke the scheduler"

    publish(_request("wakker@example.com"), db_session)
    db_session.commit()
    assert jobs._wake.is_set(), "the commit that queued a mail did not wake the scheduler"
    jobs._wake.clear()
