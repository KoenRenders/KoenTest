"""Job-handlers van het mail-component (fase 1a, #399).

``mail.retry``: herverzend een gefaalde mail vanuit de email_log-rij. De
kernel-jobtabel drijft de backoff en het maximum aantal pogingen (§5.8) — de
handler zelf gooit gewoon een uitzondering bij falen. Bij succes wordt de
bestaande log-rij op 'sent' gezet (géén nieuwe rij, anders telt één mail
dubbel in het log). Beperking: een eventuele cc staat niet in het log en
wordt bij een retry dus niet opnieuw meegenomen.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.config import settings
from app.domains.mail.models import EmailLog, MailStatus
from app.domains.mail.service import (
    SEND_JOB,
    _env_prefix,
    activity_confirmation_message,
    family_welcome_message,
    queue_mail,
)
from app.i18n import _
from app.kernel.contracts.activities import AnswerLinkSent, RegistrationConfirmed
from app.kernel.contracts.auth import CodeMailRequested
from app.kernel.contracts.mail import MailRequested
from app.kernel.contracts.membership import FamilyRegistered
from app.kernel.events import subscribe
from app.kernel.jobs import job

if TYPE_CHECKING:
    from app.domains.payment.api import TransferDue

logger = logging.getLogger(__name__)


@job("mail.retry")
def retry_mail(db: Session, payload: dict) -> None:
    log = db.get(EmailLog, payload.get("email_log_id"))
    if log is None or log.status is MailStatus.SENT:
        return  # opgeruimd of intussen alsnog verstuurd — niets te doen
    if not settings.gmail_user or not settings.gmail_app_password:
        return  # zonder credentials heeft opnieuw proberen geen zin

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{_env_prefix()}{log.subject}"
    from_address = settings.gmail_from or settings.gmail_user
    msg["From"] = f"Raak Millegem <{from_address}>"
    msg["To"] = log.recipient
    msg.attach(MIMEText(log.body or "", "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
        server.login(settings.gmail_user, settings.gmail_app_password)
        server.sendmail(settings.gmail_user, [log.recipient], msg.as_string())

    log.status = MailStatus.SENT
    log.error_message = None
    logger.info("mail.retry: e-mail aan %s alsnog verstuurd (log #%s)", log.recipient, log.id)


@job(SEND_JOB, scrub_payload=True)
def send_queued_mail(db: Session, payload: dict) -> None:
    """Send one finished message (CR-13 phase 4). Through the `_send` chokepoint, so
    logging, the demo tenant's log-only mode and the `mail.retry` job behave as
    before; `_send` is looked up when the job runs, not when it was queued."""
    from app.domains.mail import service

    service._send(
        payload["to_email"],
        payload["subject"],
        payload["body_html"],
        payload.get("cc"),
        payload.get("email_type") or "other",
    )


#: Where a signed-in person finds his registrations (CR-22; the page is
#: `activities/account_ui.py`).
MY_REGISTRATIONS = "/mijn/inschrijvingen"


@subscribe(CodeMailRequested)
def queue_code_mail(event: CodeMailRequested, db: Session) -> None:
    """The mails of a sign-in and of an account request (CR-22 R3, R4; #1707;
    the sign-in's since CR-13 phase 4d, #1251): worded here by
    kind, queued in the publisher's transaction — the one that issues the
    token — so the mail leaves only if the code it carries exists.

    Not caught: a mail that cannot be built must stop the request. Whoever
    asked for an account is told "we sent a code"; saying so while nothing
    can be sent would leave him waiting for a mail that never comes.
    """
    from app.domains.mail.service import (
        code_mail_message,
        member_contact_board_notice_message,
        sign_in_message,
    )
    from app.kernel.contracts.auth import AMBIGUOUS_ADDRESS, SIGN_IN

    if event.kind == AMBIGUOUS_ADDRESS:
        subject, body = member_contact_board_notice_message()
        queue_mail(db, event.to_email, subject, body, email_type="member_contact_notice")
        return
    if event.kind == SIGN_IN:
        subject, body = sign_in_message(event.link, event.otp_code)
        queue_mail(db, event.to_email, subject, body, email_type="magic_link")
        return
    subject, body = code_mail_message(event.kind, event.link, event.otp_code)
    # Logged under the type of the sign-in mail: the same kind of mail, a link
    # and a code to prove an address. A type of its own is a new row in the
    # code list `mail.email_type_codes`, and CR-22's one migration is merged.
    queue_mail(db, event.to_email, subject, body, email_type="magic_link")


@subscribe(MailRequested)
def on_mail_requested(event: MailRequested, db: Session) -> None:
    """Event-ingang van het mail-component (§5.8, trede 1): componenten zonder
    directe mail-afhankelijkheid publiceren MailRequested; wij versturen + loggen.

    Since CR-13 phase 4 the message is queued as a job in the publishing
    transaction, not sent from inside it: a handler never reaches the network
    (§B4.1). Measured then: nothing publishes this event yet."""
    queue_mail(
        db,
        event.to_email,
        event.subject,
        event.body_html,
        cc=event.cc,
        email_type=event.email_type,
    )


@subscribe(RegistrationConfirmed)
def queue_activity_confirmation(event: RegistrationConfirmed, db: Session) -> None:
    """The confirmation of an activity registration, built now — in the request, in
    its language — and queued to leave after the commit (CR-13 phase 4).

    A mail that cannot be built never stops the registration: that was true when the
    door sent it after the commit, and stays true here."""
    from app.domains.activities.api import Registration
    from app.domains.payment.api import PaymentRecord

    try:
        registration = db.get(Registration, event.registration_id)
        # The order lines are written inline, not through `registration.items`, so a
        # collection read earlier in the request can be stale. Flush, and let only
        # that collection load again — a full refresh would discard what the door
        # has not flushed yet.
        db.flush()
        db.expire(registration, ["items"])
        payment_record = (
            db.get(PaymentRecord, event.payment_record_id) if event.payment_record_id else None
        )
        # CR-14 §B4.8: "later" was chosen — the mail carries the answer link.
        from app.domains.activities.api import answer_path
        from app.kernel.tenant_config import tenant_base_url

        path = answer_path(db, registration.id)
        # CR-14 R6: a registration that answered "now" gets its answers repeated.
        answers = None
        if registration.form_submission_id is not None:
            from app.domains.forms.api import submission_views

            answers = submission_views(db, [registration.form_submission_id]).get(
                registration.form_submission_id
            )
        message = activity_confirmation_message(
            to_email=event.to_email,
            name=event.name,
            activity=registration.activity,
            registration=registration,
            transfer=_transfer_of(db, payment_record),
            answer_url=f"{tenant_base_url(db)}{path}" if path else None,
            answers=answers,
            # CR-22 R6 (#1707): made while signed in → it stands under Mijn
            # inschrijvingen, and the mail says where. A guest's has no person.
            history_url=(
                f"{tenant_base_url(db)}{MY_REGISTRATIONS}" if registration.person_id else None
            ),
        )
        queue_mail(db, **message)
    except Exception as e:  # noqa: BLE001 — a mail never stops a registration
        logger.error("Activiteit bevestigingsmail mislukt naar %s: %s", event.to_email, e)


@subscribe(AnswerLinkSent)
def queue_answer_link_reminder(event: AnswerLinkSent, db: Session) -> None:
    """The answer link, sent (again) by the board (CR-14 §B4.8): the confirmation
    with a reminder subject and the link, without the payment instructions — those
    went with the first mail. A mail that cannot be built never stops the action."""
    from app.domains.activities.api import Registration, answer_path
    from app.kernel.tenant_config import tenant_base_url

    try:
        registration = db.get(Registration, event.registration_id)
        path = answer_path(db, registration.id)
        if not path:
            return
        message = activity_confirmation_message(
            to_email=event.to_email,
            name=event.name,
            activity=registration.activity,
            registration=registration,
            answer_url=f"{tenant_base_url(db)}{path}",
            subject=_("Herinnering: de vragen voor %(name)s")
            % {"name": registration.activity.name},
        )
        queue_mail(db, **message)
    except Exception as e:  # noqa: BLE001 — a mail never stops the action
        logger.error("Herinnering antwoordlink mislukt naar %s: %s", event.to_email, e)


def _transfer_of(db: Session, payment_record) -> TransferDue | None:
    """How to pay this booking by transfer, as payment says it (#1775): the block
    of the confirmation mail. None for a payment that is no transfer."""
    from app.domains.payment.api import transfer_due

    return transfer_due(db, payment_record, _("Betaalinstructies (overschrijving)"))


@subscribe(FamilyRegistered)
def queue_family_welcome(event: FamilyRegistered, db: Session) -> None:
    """The welcome mail of a registered household, built now and queued to leave
    after the commit (CR-13 phase 4). It repeats the form as submitted."""
    from app.domains.membership.api import FamilyCreate
    from app.domains.payment.api import PaymentRecord

    try:
        payment_record = (
            db.get(PaymentRecord, event.payment_record_id) if event.payment_record_id else None
        )
        message = family_welcome_message(
            to_email=event.to_email,
            name=event.name,
            data=FamilyCreate.model_validate(event.form),
            pc_municipality=event.municipality,
            transfer=_transfer_of(db, payment_record),
        )
        queue_mail(db, **message)
    except Exception as e:  # noqa: BLE001 — a mail never stops a registration
        logger.error("Lidmaatschap bevestigingsmail mislukt naar %s: %s", event.to_email, e)
