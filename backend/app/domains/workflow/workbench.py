"""The workbench as a place of work (#1931; end state §5.1, §5.2).

What the two screens ask and what they may do, in one home, so the list, the
record and the POST cannot come to differ:

- **whose task it is** — a task is for one role, and that holds for the list,
  for the record and for handling it alike (`task_for`, `handle`);
- **signpost or workplace** (#822) — a subject with a screen of its own is
  handled there; here the task only points the way and cannot be ticked off;
- **the next step per kind** (Koen, 12 October 2026: "ofwel behartig je het,
  omdat het een manuele stap is … maar als het effectief een vervolgstap is,
  dan wil ik wel dat je … vanuit de lijst direct naartoe gaat") — a kind says
  itself what its button is (`next_step`);
- **what a task is about** — every domain that owns a subject describes it
  (`subjects`), for many tasks in one read.

No labels of other domains and no HTML here; the screen words what it shows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from app.domains.workflow.models import (
    KERNEL_JOB_FAILED,
    MAIL_PERMANENTLY_FAILED,
    PAYMENT_CONFIRM_REFUND,
    PAYMENT_WEBHOOK_MISMATCH,
    SubjectType,
    TaskStatus,
    WorkflowTask,
)
from app.kernel.codes import code_of

#: The kind of the one event-driven task: a message from the contact form.
MESSAGE = "bericht.behartigen"

# #822: where do you go to look at the subject, and is the workbench a SIGNPOST or
# the WORKPLACE here? Both answers hang on the SUBJECT, not on the task kind.
#
# Koen's rule, 10 September 2026: if the entity has its own screen with its own
# actions, the workbench is a signpost — *"marking a payment 'handled' from its
# workbench record is pointless"*. If all you can do is judge and note it down, the
# workbench IS the workplace: *"handling a message is a workflow action that does
# belong in the workbench, same for those mails and the kernel job."*
#
# A webhook mismatch makes that sharpest: the fix is to re-fetch the status from
# Mollie, and that button lives on the payment screen. Being able to tick
# "Handled" here would hide that the money is still not booked.
#
# Keyed on the subject rather than the kind, so a future payment task gets the right
# shape without anyone having to remember a second list.
#
# **A subject with NO screen belongs to neither.** `kernel_job` is not in this set and
# gets no link either: there is no route to a kernel-job screen, so a link would be a
# dead button rather than a signpost. What you need in order to judge it — name,
# status, attempts, last error — sits on the task's record itself, and that IS the
# way to the subject here. So do not add a link "for consistency": the point is a
# way to the thing, not a link as a shape. If you want a real screen for it, that
# is new scope.
SUBJECTS_WITH_OWN_SCREEN = {SubjectType.PAYMENT_RECORD}

#: An open task older than this counts as "Ouder dan een week".
OLD_AFTER = timedelta(days=7)


class NotHandledHere(ValueError):
    """The task points to a subject with a screen of its own (#822): it closes
    itself there, and ticking it off here would hide that the work is not done."""


def is_done(task: WorkflowTask) -> bool:
    return task.status is TaskStatus.DONE


def is_signpost(task: WorkflowTask) -> bool:
    return task.subject_type in SUBJECTS_WITH_OWN_SCREEN


def may_handle(task: WorkflowTask) -> bool:
    """Can this task be ticked off in the workbench? Not when it is done, and
    not when its subject has a screen of its own."""
    return not is_done(task) and not is_signpost(task)


def task_for(db: Session, task_id: int, roles: Sequence[str]) -> Optional[WorkflowTask]:
    """The task, for somebody with these roles — or None: a task of another
    role does not exist for them, on the record as on the list."""
    task = db.query(WorkflowTask).filter(WorkflowTask.id == task_id).first()
    if task is None or code_of(task.required_role) not in set(roles):
        return None
    return task


def handle(
    db: Session,
    task_id: int,
    roles: Sequence[str],
    *,
    done_by: str,
    decision: Optional[str] = None,
) -> Optional[WorkflowTask]:
    """Tick the task off, for somebody with these roles. None when the task is
    not theirs or does not exist; `NotHandledHere` for a signpost task. A task
    that is already done stays as it was (its decision is not overwritten)."""
    from app.domains.workflow.api import complete_task

    task = task_for(db, task_id, roles)
    if task is None:
        return None
    if is_signpost(task):
        raise NotHandledHere(task_id)
    return complete_task(db, task.id, done_by=done_by, decision=decision)


def subject_url(db: Session, task: Optional[WorkflowTask]) -> Optional[str]:
    """The way to the thing itself. Every domain supplies its own URL.

    Of the four subject types exactly one had a link before #822 (`payment_record`),
    so for three of the five task kinds there was no way to the subject at all — you
    read the title and went looking.

    `kernel_job` deliberately gets no link: there is no screen for it. Instead of a
    button pointing somewhere the job is not, the record shows its data in place. A
    dead reference is worse than none — see #811, where six of them broke at once.
    """
    if not task or not task.subject_id:
        return None
    if task.subject_type is SubjectType.PAYMENT_RECORD:
        return f"/admin/betalingen?record={task.subject_id}"
    if task.subject_type is SubjectType.EMAIL_LOG:
        from app.domains.mail.api import email_log_url

        return email_log_url(db, task.subject_id)
    if task.subject_type is SubjectType.FORM_SUBMISSION:
        from app.domains.forms.api import submission_url

        return submission_url(db, task.subject_id)
    return None


def next_step(task: WorkflowTask) -> dict[str, Any]:
    """What the row offers for this task: `{"button": step | None, "menu":
    [step, …]}`, a step being `{"do": "handle" | "subject", "label": …}`.

    `handle` ticks the task off without a decision; `subject` goes to the
    subject's own screen. A done task offers nothing. A kind this table does
    not name follows its subject: a signpost points the way, anything else is
    ticked off.
    """
    from app.i18n import _

    if is_done(task):
        return {"button": None, "menu": []}
    kind = code_of(task.kind) or ""
    handled = {"do": "handle", "label": _("Afgehandeld")}
    if kind == MESSAGE:
        return {"button": handled, "menu": [{"do": "subject", "label": _("Open de inzending")}]}
    if kind in (PAYMENT_WEBHOOK_MISMATCH, PAYMENT_CONFIRM_REFUND):
        return {"button": {"do": "subject", "label": _("Ga naar de betaling")}, "menu": []}
    if kind == MAIL_PERMANENTLY_FAILED:
        return {
            "button": {"do": "subject", "label": _("Open in de e-maillog")},
            "menu": [handled],
        }
    if kind == KERNEL_JOB_FAILED:
        return {"button": handled, "menu": []}
    if is_signpost(task):
        return {"button": {"do": "subject", "label": _("Ga naar het onderwerp")}, "menu": []}
    return {"button": handled, "menu": []}


def subjects(db: Session, tasks: Sequence[WorkflowTask]) -> dict[int, dict[str, Any]]:
    """{task id: what its subject's domain says of it}, for many tasks in one
    read per domain. A task whose subject is gone has no entry. The values are
    plain — a name, an amount, a count — and carry `type`, the subject's kind."""
    from app.domains.forms.api import submission_subjects
    from app.domains.mail.api import email_log_subjects
    from app.domains.payment.api import task_subjects
    from app.kernel.jobs import jobs_summary

    sources = {
        SubjectType.PAYMENT_RECORD: task_subjects,
        SubjectType.EMAIL_LOG: email_log_subjects,
        SubjectType.FORM_SUBMISSION: submission_subjects,
        SubjectType.KERNEL_JOB: jobs_summary,
    }
    found: dict[int, dict[str, Any]] = {}
    for subject_type, source in sources.items():
        mine = [t for t in tasks if t.subject_type is subject_type and t.subject_id]
        if not mine:
            continue
        described = source(db, [t.subject_id for t in mine])
        for task in mine:
            what = described.get(str(task.subject_id))
            if what is not None:
                found[task.id] = {"type": subject_type.value, **what}
    return found


def _belgian_day(moment: datetime):
    """The day a moment falls on for the board: the Belgian one."""
    from app.kernel.clock import belgian_day

    aware = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return belgian_day(aware)


def age_days(task: WorkflowTask, now: Optional[datetime] = None) -> Optional[int]:
    """How many days an open task has stood open, counted in Belgian days — 0
    is "today"; None for a done one."""
    if is_done(task) or task.created_at is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0, (_belgian_day(now) - _belgian_day(task.created_at)).days)


def figures(mine: Sequence[WorkflowTask], now: Optional[datetime] = None) -> dict[str, int]:
    """The figures of the list's title row and segments, over all of a viewer's
    tasks — whatever the list is filtered on: how many are open, how many came
    in today, how many open ones are older than a week, and how many are done."""
    now = now or datetime.now(timezone.utc)
    open_ = [t for t in mine if not is_done(t)]
    return {
        "open": len(open_),
        "today": sum(
            1 for t in mine if t.created_at and _belgian_day(t.created_at) == _belgian_day(now)
        ),
        "old": sum(1 for t in open_ if (age_days(t, now) or 0) > OLD_AFTER.days),
        "done": len(mine) - len(open_),
    }
