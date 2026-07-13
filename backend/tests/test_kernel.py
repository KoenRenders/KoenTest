"""Kernel-tests (#396): event-dispatcher (in-transactie-semantiek) en het
achtergrondwerk-primitief (enqueue, retry met backoff, definitief falen)."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.kernel import events
from app.kernel.events import KernelEvent, publish, subscribe
from app.kernel.jobs import KernelJob, _handlers, enqueue, job, run_due_jobs


@dataclass(frozen=True)
class PingEvent(KernelEvent):
    value: int


@pytest.fixture(autouse=True)
def _clean_registries():
    yield
    events.reset_subscribers()
    _handlers.clear()


# ── events ─────────────────────────────────────────────────────────────────────

def test_publish_reaches_all_handlers_synchronously(db_session):
    seen = []
    subscribe(PingEvent)(lambda e, db: seen.append(("a", e.value)))
    subscribe(PingEvent)(lambda e, db: seen.append(("b", e.value)))

    publish(PingEvent(value=7), db_session)
    assert seen == [("a", 7), ("b", 7)]  # synchroon, in volgorde


def test_handler_failure_propagates_to_publisher(db_session):
    """Trede 1 van de event-ladder: een handler-fout rolt de bron mee terug —
    de fout MOET dus bij de publisher aankomen, niet stil verdwijnen."""
    @subscribe(PingEvent)
    def boom(event, db):
        raise RuntimeError("handler stuk")

    with pytest.raises(RuntimeError, match="handler stuk"):
        publish(PingEvent(value=1), db_session)


def test_publish_without_subscribers_is_noop(db_session):
    publish(PingEvent(value=0), db_session)  # geen fout


# ── jobs ───────────────────────────────────────────────────────────────────────

def test_job_runs_and_completes(db_session):
    done = []
    job("test.ok")(lambda db, payload: done.append(payload["x"]))
    enqueue(db_session, "test.ok", {"x": 42})
    db_session.commit()

    assert run_due_jobs(db_session) == 1
    assert done == [42]
    entry = db_session.query(KernelJob).filter(KernelJob.name == "test.ok").one()
    assert entry.status == "done" and entry.attempts == 1


def test_job_failure_retries_with_backoff_then_fails(db_session):
    @job("test.fail")
    def always_fail(db, payload):
        raise ValueError("kapot")

    enqueue(db_session, "test.fail", max_attempts=2)
    db_session.commit()

    run_due_jobs(db_session)
    entry = db_session.query(KernelJob).filter(KernelJob.name == "test.fail").one()
    assert entry.status == "pending" and entry.attempts == 1
    assert "kapot" in entry.last_error
    assert entry.run_at > datetime.now(timezone.utc)  # backoff gepland

    # Forceer de retry nu en laat hem definitief falen.
    entry.run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    run_due_jobs(db_session)
    db_session.expire_all()
    assert entry.status == "failed" and entry.attempts == 2


def test_job_without_handler_fails_loud(db_session):
    enqueue(db_session, "test.onbekend", max_attempts=1)
    db_session.commit()
    run_due_jobs(db_session)
    entry = db_session.query(KernelJob).filter(KernelJob.name == "test.onbekend").one()
    assert entry.status == "failed"
    assert "geen handler" in entry.last_error


def test_future_job_is_not_picked_up(db_session):
    job("test.later")(lambda db, payload: None)
    enqueue(db_session, "test.later", run_at=datetime.now(timezone.utc) + timedelta(hours=1))
    db_session.commit()
    assert run_due_jobs(db_session) == 0
