"""Event-abonnementen en jobs van workflow (fase 4b, #403).

- ``SubmissionCreated`` (berichten) start de 'bericht'-workflowdefinitie
  (behartigen) — de P-blok-kern, nu veralgemeend via definities.
- ``workflow.sweep``: vult de werkbank vanuit de overige bronnen — pending
  refunds (consolidatie van de bestaande wachtrij), definitief gefaalde mails,
  webhook-mismatches en definitief gefaalde jobs. Idempotent per onderwerp
  (titel = sleutel); zero-touch als ontwerpdoel — een lege werkbank is gezond.
  Kill-switch: settings.workbench_enabled.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.domains.workflow import api
from app.kernel.contracts.forms import SubmissionCreated
from app.kernel.events import subscribe
from app.kernel.jobs import enqueue, job

logger = logging.getLogger(__name__)

BERICHTEN_SLUG = "berichten"
SWEEP_INTERVAL = timedelta(hours=1)


@subscribe(SubmissionCreated)
def create_behartigen_task(event: SubmissionCreated, db: Session) -> None:
    if event.form_slug != BERICHTEN_SLUG:
        return
    afzender = event.submitter_name or "onbekende afzender"
    api.start(db, "bericht", subject_type="form_submission",
              subject_id=event.submission_id, context={"afzender": afzender})


def _sweep_sources(db: Session) -> list[dict]:
    """De taak-kandidaten van de 4 sweep-bronnen (behartigen is event-gedreven)."""
    from app.domains.mail.api import EmailLog
    from app.domains.payment.api import GatewayPayment, PaymentRecord
    from app.kernel.jobs import KernelJob

    kandidaten: list[dict] = []

    # 1. Refund-bevestiging (consolidatie): pending refunds wachten op FINANCE.
    for r in (db.query(PaymentRecord)
              .filter(PaymentRecord.type == "refund", PaymentRecord.status == "pending").all()):
        kandidaten.append(dict(
            kind="payment.refund_bevestigen",
            title=f"Refund {r.id} bevestigen ({r.payable_type} #{r.payable_id})",
            subject_type="payment_record", subject_id=r.payable_id, role="FINANCE"))

    # 2. Definitief gefaalde mails (na de mail.retry-pogingen).
    failed_mail_jobs = {j.payload.get("email_log_id")
                       for j in db.query(KernelJob)
                       .filter(KernelJob.name == "mail.retry", KernelJob.status == "failed").all()}
    for log_id in sorted(x for x in failed_mail_jobs if x):
        log = db.get(EmailLog, log_id)
        if log is None or log.status == "sent":
            continue
        kandidaten.append(dict(
            kind="mail.definitief_gefaald",
            title=f"E-mail #{log.id} aan {log.recipient} definitief gefaald",
            subject_type="email_log", subject_id=log.id, role="ADMIN"))

    # 3. Webhook-mismatch: gateway zegt paid, het grootboek (nog) niet.
    rows = (db.query(GatewayPayment, PaymentRecord)
            .join(PaymentRecord, PaymentRecord.gateway_payment_id == GatewayPayment.id)
            .filter(GatewayPayment.status == "paid", PaymentRecord.status != "paid").all())
    for gp, record in rows:
        kandidaten.append(dict(
            kind="payment.webhook_mismatch",
            title=f"Webhook-mismatch: gateway {gp.id[:8]}… is paid, record {record.id[:8]}… is {record.status}",
            subject_type="payment_record", subject_id=record.payable_id, role="FINANCE"))

    # 4. Definitief gefaalde jobs (behalve mail.retry — bron 2 dekt die met context).
    for j in (db.query(KernelJob)
              .filter(KernelJob.status == "failed", KernelJob.name != "mail.retry").all()):
        kandidaten.append(dict(
            kind="kernel.job_gefaald",
            title=f"Job {j.name} (#{j.id}) definitief gefaald: {(j.last_error or '')[:120]}",
            subject_type="kernel_job", subject_id=j.id, role="ADMIN"))

    return kandidaten


# De soorten die de sweep zélf maakt. Alleen déze mag hij ook sluiten (#675):
# `payment.wees_record` komt uit een andere job en `bericht.behartigen` is
# event-gedreven, dus van hun bestaan weet `_sweep_sources` niets. Zou de sweep
# "alles wat niet meer matcht" sluiten, dan sluit hij taken waarvan hij de
# aanleiding nooit heeft gekend.
SWEEP_SOORTEN = frozenset({
    "payment.refund_bevestigen", "mail.definitief_gefaald",
    "payment.webhook_mismatch", "kernel.job_gefaald",
})


@job("workflow.sweep")
def sweep(db: Session, payload: dict) -> None:
    # Lazy, zoals elders in dit domein: _() moet de taal van de actieve tenant
    # volgen en niet die van het importmoment.
    from app.i18n import _

    if settings.workbench_enabled:
        open_taken = api.open_tasks(db, ["ADMIN", "FINANCE"])
        bestaande = {t.title for t in open_taken}
        kandidaten = _sweep_sources(db)
        for kandidaat in kandidaten:
            if kandidaat["title"] in bestaande:
                continue
            logger.warning("werkbank-sweep: nieuwe taak — %s", kandidaat["title"])
            api.create_task(db, kind=kandidaat["kind"], title=kandidaat["title"],
                            subject_type=kandidaat["subject_type"],
                            subject_id=kandidaat["subject_id"],
                            required_role=kandidaat["role"])

        # Andersom (#675): een open taak die niet meer in de kandidatenlijst staat,
        # heeft haar aanleiding verloren — de refund is uitbetaald, de mismatch is
        # weg. Tot nu sloot geen enkele taak zichzelf: `close_task` werd alleen
        # vanuit de werkbank aangeroepen, dus zulke taken bleven eeuwig staan.
        #
        # Dezelfde titels als sleutel, dus geen nieuw mechanisme — het is de
        # spiegel van de idempotentiecheck hierboven. En `done_by="systeem"` met een
        # reden in `decision`, want anders toont het archief uit #674 taken die door
        # niemand afgehandeld lijken.
        geldig = {k["title"] for k in kandidaten}
        for taak in open_taken:
            if taak.kind in SWEEP_SOORTEN and taak.title not in geldig:
                logger.warning("werkbank-sweep: aanleiding weg — %s", taak.title)
                api.close_task(db, taak.id, done_by="systeem",
                               decision=_("Automatisch gesloten: de aanleiding voor "
                                          "deze taak bestaat niet meer."))
    if not payload.get("once"):
        enqueue(db, "workflow.sweep", {},
                run_at=datetime.now(timezone.utc) + SWEEP_INTERVAL)
