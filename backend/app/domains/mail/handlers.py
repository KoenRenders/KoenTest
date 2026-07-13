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

from sqlalchemy.orm import Session

from app.config import settings
from app.domains.mail.models import EmailLog
from app.domains.mail.service import _dispatch, _env_prefix
from app.kernel.contracts.mail import MailRequested
from app.kernel.events import subscribe
from app.kernel.jobs import job

logger = logging.getLogger(__name__)


@job("mail.retry")
def retry_mail(db: Session, payload: dict) -> None:
    log = db.get(EmailLog, payload.get("email_log_id"))
    if log is None or log.status == "sent":
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

    log.status = "sent"
    log.error_message = None
    logger.info("mail.retry: e-mail aan %s alsnog verstuurd (log #%s)", log.recipient, log.id)


@subscribe(MailRequested)
def on_mail_requested(event: MailRequested, db: Session) -> None:
    """Event-ingang van het mail-component (§5.8, trede 1): componenten zonder
    directe mail-afhankelijkheid publiceren MailRequested; wij versturen + loggen.
    De verzending zelf loopt via het bestaande _send-chokepoint (incl. skipped/
    failed-logging en de mail.retry-job) en gebeurt synchroon in de handler —
    de publicerende transactie is dan al geslaagd of rolt óók terug."""
    _dispatch(None, event.to_email, event.subject, event.body_html,
              cc=event.cc, email_type=event.email_type)
