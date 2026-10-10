"""A reading nobody hears fails its job — it does not end "done" (CR-13 phase 4d, #1251).

Since the cut, media's reading job says what it read (`DocumentTextExtracted`)
and the chatbot keeps it. A process that did not register the chatbot's handler
would read documents and lose the text. The job refuses that — and the refusal
must be LOUD: in the first build it was raised inside the reading's own catch,
which turns every failure into one warning, so the job ended "done" (found in
dev2's review of the pull request). It is raised before that catch now.

Run through the job runner, as the scheduler runs it: the job's own row says
how it ended.

Red proof: the check moved back inside the `try` → both tests of the silent
process fail, the job ends "done".
"""

from __future__ import annotations

import app.domains.media.extraction as mx
from app.domains.media.service import EXTRACT_JOB
from app.kernel import events
from app.kernel.contracts.media import DocumentTextExtracted
from app.kernel.jobs import JobStatus, enqueue, run_due_jobs


def _nobody_listens(monkeypatch) -> None:
    monkeypatch.setitem(events._subscribers, DocumentTextExtracted, [])
    assert not events.has_subscribers(DocumentTextExtracted)


def _reader_calls(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(mx, "extract_document_text", lambda *a, **k: calls.append(a) or "tekst")
    return calls


def test_the_job_fails_when_nobody_listens(db_session, monkeypatch):
    _nobody_listens(monkeypatch)
    calls = _reader_calls(monkeypatch)
    job = enqueue(db_session, EXTRACT_JOB, {"asset_id": 880_101}, max_attempts=1)
    db_session.flush()

    run_due_jobs(db_session)

    db_session.refresh(job)
    assert job.status is JobStatus.FAILED
    assert "DocumentTextExtracted" in job.last_error
    assert calls == [], "a document was read for nobody"


def test_the_job_is_tried_again_and_is_not_done(db_session, monkeypatch):
    """With the attempts a job normally gets: back in the queue with its error,
    for when the process is put right — not marked done."""
    _nobody_listens(monkeypatch)
    job = enqueue(db_session, EXTRACT_JOB, {"asset_id": 880_102})
    db_session.flush()

    run_due_jobs(db_session)

    db_session.refresh(job)
    assert job.status is JobStatus.PENDING
    assert job.attempts == 1
    assert "DocumentTextExtracted" in job.last_error


def test_with_the_application_listening_the_job_ends_done(db_session, monkeypatch):
    """The other side: the handler `app.main` registers is there, the asset is not
    — nothing to read, and that is a finished job."""
    calls = _reader_calls(monkeypatch)
    job = enqueue(db_session, EXTRACT_JOB, {"asset_id": 880_103})
    db_session.flush()

    run_due_jobs(db_session)

    db_session.refresh(job)
    assert job.status is JobStatus.DONE
    assert job.last_error is None
    assert calls == []
