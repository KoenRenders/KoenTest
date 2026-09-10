"""Remove the leftover ``payment.reconcile`` queue rows (#858, aftermath of #824).

**The rule underneath, and it is the reason this file exists: removing a job handler is
not finished while its queue still holds rows.** #824 deleted the orphan-payment
mechanism and with it ``payment/handlers.py``, including the ``payment.reconcile`` job.
The code was consistent afterwards; the table was not. That difference only shows when a
scheduled row comes up — up to a day later. So when you remove a job, clean out its
queue in the same migration.

What happened, measured on HDEV on 10 September 2026: the job rescheduled itself daily,
59 rows since the start of September, all ``done`` but one. Row 1432 was created by the
run of 9 September, was due on 10 September, found no handler, tried **five times**, gave
up, and put a ``kernel.job_gefaald`` task on the treasurer's workbench. Nothing broke and
no money was involved — but it is an error message about a mechanism that was removed on
purpose, on the screen of somebody who can do nothing with it.

It is not recurring: a failed row schedules no successor, and nothing in the tree enqueues
``payment.reconcile`` any more. UAT and PROD, however, still carry a ``pending`` row from
the same daily chain. Hence a migration: every environment gets this at deploy time.

**Why the ``failed`` row goes too, and not only the pending ones.** The issue asks to keep
the history and close the task that already exists. Those two cannot both hold while the
failed row stays: the sweep builds its candidates from ``status = 'failed'``, so a closed
task is simply re-created on the next hourly round, forever. That row is not a report of a
run either — it is the artefact of removing the handler. Its content survives in the
closing note on the task. The 58 ``done`` rows are the actual report and are left exactly
as they are.

Idempotent: on a clean environment nothing matches and nothing changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "098"
down_revision = "097"
branch_labels = None
depends_on = None

JOB_NAME = "payment.reconcile"
CLOSING_NOTE = (
    "Het wees-betalingmechanisme is verwijderd (#824), dus deze job heeft geen handler "
    "meer. De ingeplande rij is opgeruimd (#858); er is niets meer te doen."
)


def _cleanup(bind) -> int:
    """Neutralise the leftovers. Returns the number of tasks closed.

    Split out of ``upgrade()`` so a test can drive it against a session: a migration is a
    snapshot and must not import application code, but that must not make it untestable
    either.
    """
    # The ids first: after the delete below there is nothing left to match the tasks on.
    # Matching on the SUBJECT and not on the title text — the title is display copy and
    # may be reworded, while `subject_id` is what the sweep itself writes.
    ids = [row[0] for row in bind.execute(sa.text(
        "SELECT id FROM kernel_jobs WHERE name = :n AND status IN ('pending', 'failed')"),
        {"n": JOB_NAME}).fetchall()]
    if not ids:
        return 0

    # Only open tasks about THESE jobs. Tasks about other failed jobs must stay — that is
    # the same trap as the sweep in #675, where "everything that no longer fits" would
    # close far too much.
    closed = bind.execute(sa.text(
        "UPDATE workflow.workflow_tasks SET status = 'done', done_at = now(), "
        "done_by = 'systeem', decision = :note "
        "WHERE kind = 'kernel.job_gefaald' AND status = 'open' "
        "AND subject_type = 'kernel_job' AND subject_id = ANY(:ids)"),
        {"note": CLOSING_NOTE, "ids": [str(i) for i in ids]}).rowcount

    bind.execute(sa.text(
        "DELETE FROM kernel_jobs WHERE name = :n AND status IN ('pending', 'failed')"),
        {"n": JOB_NAME})
    return closed or 0


def upgrade() -> None:
    _cleanup(op.get_bind())


def downgrade() -> None:
    """Deliberately empty.

    Putting back a queue row for a handler that does not exist would recreate the exact
    failure this migration removes. The 58 ``done`` rows were never touched, so there is
    nothing to restore.
    """
