"""#858 — a job handler removed, its queue left behind.

Aftermath of #824. That issue deleted the orphan-payment mechanism and with it the
``payment.reconcile`` job; the code was consistent afterwards, the table was not. On HDEV
the daily chain had one row left over: created on 9 September, due on 10 September, no
handler, five attempts, gave up, and a ``kernel.job_gefaald`` task on the treasurer's
workbench.

**The rule this pins down: removing a job handler is not finished while its queue still
holds rows.** The difference between "gone from the code" and "gone from the running
installation" only shows when a scheduled row comes up — up to a day later.

Migration 098 does the cleanup, and these tests drive its ``_cleanup`` directly. That
function is split out of ``upgrade()`` for exactly this reason: a migration is a snapshot
and must not import application code, but that must not make it untestable either.

**The trap is the width of the cleanup.** Tasks about OTHER failed jobs have to stay. That
is the same trap as the sweep in #675, where "everything that no longer fits" would close
far too much — hence `test_a_task_about_another_job_is_left_alone`.

And one property the issue does not name but that decides whether it works at all: the
sweep builds its candidates from ``status = 'failed'``, so closing the task while leaving
the failed row means the task returns on the next hourly round. `test_the_task_stays_closed_after_a_sweep`
is the one that catches that; it is why the failed row goes too and the 58 ``done`` rows
do not.

Broken on purpose to check that these tests can go red: restricted the delete to
``'pending'`` → the sweep test falls over with the task reopened; dropped the
``subject_id`` condition from the UPDATE → the other-job test falls over with a task
closed that nobody asked about.
"""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.kernel.jobs import KernelJob
from app.domains.workflow.models import WorkflowTask

pytestmark = pytest.mark.ui_agnostisch

JOB_NAME = "payment.reconcile"
MIGRATION = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
             / "098_drop_payment_reconcile_queue.py")


def _cleanup(db):
    spec = importlib.util.spec_from_file_location("migration_098", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module._cleanup(db.connection())
    db.expire_all()
    return result


def _job(db, *, name=JOB_NAME, status="pending", error=None):
    entry = KernelJob(name=name, payload={}, status=status,
                      run_at=datetime.now(timezone.utc) - timedelta(hours=1),
                      attempts=5 if status == "failed" else 0, max_attempts=5,
                      last_error=error)
    db.add(entry)
    db.flush()
    return entry


def _failed_job_task(db, job):
    task = WorkflowTask(
        kind="kernel.job_gefaald",
        title=f"Job {job.name} (#{job.id}) definitief gefaald: {job.last_error or ''}",
        subject_type="kernel_job", subject_id=str(job.id),
        status="open", required_role="ADMIN")
    db.add(task)
    db.flush()
    return task


def test_a_waiting_row_is_gone_and_the_history_is_untouched(db_session):
    """UAT and PROD carry exactly this: a pending row from the same daily chain, waiting
    to fail as soon as v2.2 runs there."""
    _job(db_session, status="pending")
    history = [_job(db_session, status="done") for _ in range(3)]

    _cleanup(db_session)

    remaining = (db_session.query(KernelJob)
                 .filter(KernelJob.name == JOB_NAME).all())
    assert [j.status for j in remaining] == ["done"] * 3, (
        "either the waiting row survived, or the history was taken along — those 58 "
        "successful runs are a report and there is nothing wrong with them")
    assert {j.id for j in remaining} == {j.id for j in history}


def test_a_clean_environment_does_not_change(db_session):
    """Idempotent, like every migration here. Also what happens on the second deploy."""
    other = _job(db_session, name="workflow.sweep", status="pending")

    assert _cleanup(db_session) == 0
    assert _cleanup(db_session) == 0

    db_session.expire_all()
    assert db_session.query(KernelJob).filter(KernelJob.id == other.id).one()


def test_an_existing_task_is_closed_with_a_readable_reason(db_session):
    """On HDEV this task is already on the workbench. A closing reason that says the
    mechanism was removed — not an empty system note nobody can use in six months."""
    failed = _job(db_session, status="failed",
                  error="LookupError: geen handler geregistreerd voor job 'payment.reconcile'")
    task = _failed_job_task(db_session, failed)

    assert _cleanup(db_session) == 1

    db_session.refresh(task)
    assert task.status == "done" and task.done_by == "systeem"
    assert "#824" in (task.decision or "") and "#858" in (task.decision or ""), (
        f"the reason does not say why this was removed: {task.decision!r}")


def test_the_task_stays_closed_after_a_sweep(db_session):
    """The property that decides whether this works at all.

    The sweep builds its candidates from `status = 'failed'`. Leave that row and the
    closed task is simply re-created on the next hourly round — forever. This is why the
    failed row goes too, while the successful history stays.
    """
    from app.domains.workflow.handlers import sweep

    failed = _job(db_session, status="failed", error="LookupError: geen handler")
    _failed_job_task(db_session, failed)
    _cleanup(db_session)

    sweep(db_session, {"once": True})

    db_session.expire_all()
    still_open = (db_session.query(WorkflowTask)
                  .filter(WorkflowTask.kind == "kernel.job_gefaald",
                          WorkflowTask.status == "open").all())
    assert not [t for t in still_open if JOB_NAME in t.title], (
        "the sweep put the task back, so the cleanup only lasted until the next round")


def test_a_task_about_another_job_is_left_alone(db_session):
    """The width of the cleanup, and the same trap as #675.

    Another job that really did fail keeps its task: that one has a reason to be there,
    and closing it would hide a real failure behind this cleanup.
    """
    other = _job(db_session, name="mail.digest", status="failed", error="boom")
    other_task = _failed_job_task(db_session, other)
    _job(db_session, status="pending")

    _cleanup(db_session)

    db_session.refresh(other_task)
    assert other_task.status == "open", (
        "a task about another failed job was closed as well — the cleanup grabs too wide")
    assert db_session.query(KernelJob).filter(KernelJob.id == other.id).one().status == "failed"
