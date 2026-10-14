"""Event-abonnementen en jobs van workflow (fase 4b, #403).

- ``SubmissionCreated`` (berichten) start de 'bericht'-workflowdefinitie
  (behartigen) — de P-blok-kern, nu veralgemeend via definities.
- ``workflow.sweep``: vult de werkbank vanuit de overige bronnen — pending
  refunds (consolidatie van de bestaande wachtrij), definitief gefaalde mails,
  webhook-mismatches en definitief gefaalde jobs. Idempotent per onderwerp
  (soort en onderwerp = sleutel, sinds #1994; de titel is enkel tekst); zero-touch als ontwerpdoel — een lege werkbank is gezond.
  Kill-switch: settings.workbench_enabled.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.domains.forms.api import CONTACT_FORM_SLUG
from app.domains.workflow import api
from app.domains.workflow.api import (
    KERNEL_JOB_FAILED,
    MAIL_PERMANENTLY_FAILED,
    PAYMENT_CONFIRM_REFUND,
    PAYMENT_WEBHOOK_MISMATCH,
)
from app.i18n import _
from app.kernel.contracts.forms import SubmissionCreated, SubmissionDeleted
from app.kernel.contracts.mdm import TenantCreated
from app.kernel.contracts.payment import PaymentReceived, RefundDue
from app.kernel.events import subscribe
from app.kernel.jobs import enqueue, job

logger = logging.getLogger(__name__)

SWEEP_INTERVAL = timedelta(hours=1)


@subscribe(PaymentReceived)
@subscribe(RefundDue)
def advance_sweep_on_money(event: PaymentReceived | RefundDue, db: Session) -> None:
    """Look at the workbench now, not at the next hourly round (#705, #855).

    Until CR-13 phase 2 `payment` called `vervroeg_sweep` itself, after "bevestig
    betaald" and after creating a refund. Now it says what happened, and this does
    what those two calls did — advance the sweep, never make or close a task: the
    sweep decides which tasks exist, by their kind and subject (#705, #1994). Every way
    money comes in publishes `PaymentReceived`, a provider's webhook included.
    """
    api.vervroeg_sweep(db)


@subscribe(SubmissionCreated)
def create_behartigen_task(event: SubmissionCreated, db: Session) -> None:
    # #1377: the slug comes from forms, its one home, not from a copy here.
    if event.form_slug != CONTACT_FORM_SLUG:
        return
    afzender = event.submitter_name or "onbekende afzender"
    api.start(
        db,
        api.MESSAGE_WORKFLOW,
        subject_type="form_submission",
        subject_id=str(event.submission_id),
        context={"afzender": afzender},
    )


@subscribe(SubmissionDeleted)
def close_task_of_deleted_submission(event: SubmissionDeleted, db: Session) -> None:
    """A deleted submission closes its open task (#1377).

    Deleting spam through "Contacteer ons" left its task on the werkbank, pointing
    at a submission that no longer existed. No slug check: a task is found by its
    subject, so the submission of any other form has none and nothing happens.
    """
    api.close_subject_tasks(
        db,
        api.SubjectType.FORM_SUBMISSION,
        str(event.submission_id),
        reason=_("Automatisch gesloten: inzending verwijderd."),
    )


def _sweep_sources(db: Session) -> list[dict]:
    """De taak-kandidaten van de 4 sweep-bronnen (behartigen is event-gedreven)."""
    from app.domains.mail.api import EMAIL_TYPE, EmailLog, MailStatus
    from app.domains.payment.api import (
        PAYABLE_TYPE,
        PAYMENT_PROVIDER,
        PAYMENT_STATUS,
        GatewayPayment,
        PaymentRecord,
        PaymentStatus,
        PaymentType,
    )
    from app.kernel.codes import code_label
    from app.kernel.jobs import JobStatus, KernelJob

    kandidaten: list[dict] = []

    # 1. Refund-bevestiging (consolidatie): pending refunds wachten op FINANCE.
    for r in (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.type == PaymentType.REFUND, PaymentRecord.status == PaymentStatus.PENDING
        )
        .all()
    ):
        # #1991: the payment in words — the payable's label from payment's own
        # code list ("Lidmaatschap" → "lidmaatschap"), with its number. The
        # record's id says nothing to the treasurer; it stays the subject.
        wat = code_label(PAYABLE_TYPE.name, r.payable_type)
        kandidaten.append(
            dict(
                kind=PAYMENT_CONFIRM_REFUND,
                title=f"Terugbetaling {wat[:1].lower()}{wat[1:]} #{r.payable_id} bevestigen",
                # #704: het record-id, niet het payable — `subject_type` zegt
                # "payment_record" en de waarde hoort dat te zijn.
                subject_type="payment_record",
                subject_id=str(r.id),
                role="FINANCE",
            )
        )

    # 2. Definitief gefaalde mails (na de mail.retry-pogingen).
    failed_mail_jobs = {
        j.payload.get("email_log_id")
        for j in db.query(KernelJob)
        .filter(KernelJob.name == "mail.retry", KernelJob.status == JobStatus.FAILED)
        .all()
    }
    for log_id in sorted(x for x in failed_mail_jobs if x):
        log = db.get(EmailLog, log_id)
        if log is None or log.status is MailStatus.SENT:
            continue
        # #1994: what kind of mail, from mail's own code list. The address
        # is not in the title: the task's record shows it (with a link to
        # write), the list's second line shows the mail's subject, and a
        # title travels into logs and lists that need no address.
        kandidaten.append(
            dict(
                kind=MAIL_PERMANENTLY_FAILED,
                title=f"E-mail ({code_label(EMAIL_TYPE.name, log.email_type)}) niet afgeleverd",
                subject_type="email_log",
                subject_id=str(log.id),
                role="ADMIN",
            )
        )

    # 3. Webhook-mismatch: gateway zegt paid, het grootboek (nog) niet.
    rows = (
        db.query(GatewayPayment, PaymentRecord)
        .join(PaymentRecord, PaymentRecord.gateway_payment_id == GatewayPayment.id)
        # `GatewayPayment.status` carries Mollie's word (§B4.10) and so
        # stays a string; `PaymentRecord.status` is our list.
        .filter(
            GatewayPayment.status == PaymentStatus.PAID.value,
            PaymentRecord.status != PaymentStatus.PAID,
        )
        .all()
    )
    for gp, record in rows:
        kandidaten.append(
            dict(
                kind=PAYMENT_WEBHOOK_MISMATCH,
                # #1994: who says paid, and what our ledger says — both from
                # payment's code lists; the ids stay on the record.
                title=(
                    f"Betaald volgens {code_label(PAYMENT_PROVIDER.name, gp.provider)}, "
                    f"hier {code_label(PAYMENT_STATUS.name, record.status).lower()}: nakijken"
                ),
                subject_type="payment_record",
                subject_id=str(record.id),
                role="FINANCE",
            )
        )

    # 4. Definitief gefaalde jobs (behalve mail.retry — bron 2 dekt die met context).
    for j in (
        db.query(KernelJob)
        .filter(KernelJob.status == JobStatus.FAILED, KernelJob.name != "mail.retry")
        .all()
    ):
        kandidaten.append(
            dict(
                kind=KERNEL_JOB_FAILED,
                # #1994: a job has no Dutch word of its own (its name is a
                # code), so the title says what happened; the list's second
                # line names the job and its attempts, and the error text
                # stays on the job.
                title="Achtergrondtaak definitief mislukt",
                subject_type="kernel_job",
                subject_id=str(j.id),
                role="ADMIN",
            )
        )

    return kandidaten


# De soorten die de sweep zélf maakt. Alleen déze mag hij ook sluiten (#675):
# `bericht.behartigen` is event-driven, so `_sweep_sources` knows nothing of its
# existence. If the sweep closed "everything that no longer matches", it would close
# tasks whose cause it never knew about.
#
# (#824: `payment.wees_record` used to be listed here too, for the same reason. That
# mechanism is gone entirely.)
SWEEP_SOORTEN = frozenset(
    {
        "payment.refund_bevestigen",
        "mail.definitief_gefaald",
        "payment.webhook_mismatch",
        "kernel.job_gefaald",
    }
)


def _task_key(kind, subject_type, subject_id) -> tuple[str, str, str]:
    """A sweep task's key: its kind and its subject (#1994), as text."""
    return (str(kind), str(getattr(subject_type, "value", subject_type)), str(subject_id))


@job("workflow.sweep")
def sweep(db: Session, payload: dict) -> None:
    # Lazy, zoals elders in dit domein: _() moet de taal van de actieve tenant
    # volgen en niet die van het importmoment.
    from app.i18n import _

    if settings.workbench_enabled:
        open_taken = api.open_tasks(db, ["ADMIN", "FINANCE"])
        kandidaten = _sweep_sources(db)
        # The key of a task is its kind and its subject (#1994), not its
        # title: a title in words need not be unique — two pending refunds on
        # one payable read alike — and a title may change. Until #1994 the
        # title was the key, and the second of two such refunds got no task.
        current = {_task_key(k["kind"], k["subject_type"], k["subject_id"]): k for k in kandidaten}
        # #1991: an open task whose cause is still there, under a title that
        # was built otherwise when it was made, gets the title its cause has
        # now — the same task, its history kept.
        hertiteld = False
        bestaande = set()
        for taak in open_taken:
            key = _task_key(taak.kind, taak.subject_type, taak.subject_id)
            bestaande.add(key)
            kandidaat = current.get(key)
            if taak.kind in SWEEP_SOORTEN and kandidaat and taak.title != kandidaat["title"]:
                logger.warning("werkbank-sweep: nieuwe titel — %s #%s", taak.kind, taak.id)
                taak.title = kandidaat["title"]
                hertiteld = True
        if hertiteld:
            db.flush()
        for key, kandidaat in current.items():
            if key in bestaande:
                continue
            # Kind and subject only in the log: a title is for the screen.
            logger.warning(
                "werkbank-sweep: nieuwe taak — %s %s", kandidaat["kind"], kandidaat["subject_id"]
            )
            api.create_task(
                db,
                kind=kandidaat["kind"],
                title=kandidaat["title"],
                subject_type=kandidaat["subject_type"],
                subject_id=kandidaat["subject_id"],
                required_role=kandidaat["role"],
            )

        # Andersom (#675): een open taak die niet meer in de kandidatenlijst staat,
        # heeft haar aanleiding verloren — de refund is uitbetaald, de mismatch is
        # weg. Tot nu sloot geen enkele taak zichzelf: `close_task` werd alleen
        # vanuit de werkbank aangeroepen, dus zulke taken bleven eeuwig staan.
        #
        # Dezelfde sleutel (soort en onderwerp, #1994), dus geen nieuw mechanisme —
        # het is de spiegel van de idempotentiecheck hierboven. En `done_by="systeem"`
        # met een reden in `decision`, want anders toont het archief uit #674 taken
        # die door niemand afgehandeld lijken.
        gesloten = False
        for taak in open_taken:
            key = _task_key(taak.kind, taak.subject_type, taak.subject_id)
            if taak.kind in SWEEP_SOORTEN and key not in current:
                logger.warning("werkbank-sweep: aanleiding weg — %s #%s", taak.kind, taak.id)
                api.close_task(
                    db,
                    taak.id,
                    done_by="systeem",
                    decision=_(
                        "Automatisch gesloten: de aanleiding voor deze taak bestaat niet meer."
                    ),
                )
                gesloten = True
        # close_task zet enkel de velden; het wegschrijven hoort bij de aanroeper.
        # Zonder deze flush blijft de wijziging in de sessie hangen tot iets anders
        # ze toevallig meeneemt — en dan is "de taak is gesloten" afhankelijk van
        # wat er ná deze job gebeurt.
        if gesloten:
            db.flush()
    if not payload.get("once"):
        enqueue(db, "workflow.sweep", {}, run_at=datetime.now(timezone.utc) + SWEEP_INTERVAL)


@subscribe(TenantCreated)
def seed_message_workflow_of_new_tenant(event: TenantCreated, db: Session) -> None:
    """A new tenant can take a contact message: its own "bericht" (#1509)."""
    api.seed_message_workflow(db, event.tenant_id)
