import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Optional

from app.config import settings
from app.domains.activities.api import compute_registration_total
from app.i18n import _

logger = logging.getLogger(__name__)


def _env_prefix() -> str:
    env = (settings.app_env or "").lower()
    if env in ("dev", "hdev", "uat"):
        return f"[{env.upper()}] "
    return ""


def _dispatch(
    background_tasks,
    to_email: str,
    subject: str,
    body_html: str,
    cc: Optional[str] = None,
    email_type: str = "other",
) -> None:
    """Verstuur de mail. Met een FastAPI BackgroundTasks wordt de trage SMTP-call
    ná de response uitgevoerd (#78); zonder, synchroon (bv. in scripts/tests).
    De mailtekst is op dit punt al opgebouwd, dus er is geen DB-sessie meer nodig."""
    if background_tasks is not None:
        background_tasks.add_task(_send, to_email, subject, body_html, cc, email_type)
    else:
        _send(to_email, subject, body_html, cc, email_type)


def _log_email(to_email: str, subject: str, body_html: str, email_type: str, status: str, error: Optional[str]) -> Optional[int]:
    """Schrijf één rij naar de centrale email_log (#328). Loggen mag het versturen
    nooit breken: alle fouten worden hier opgevangen. Gebruikt een eigen
    SessionLocal omdat _send vaak in een BackgroundTask draait (geen request-sessie).
    Geeft het log-id terug (voor de retry-job), of None als het loggen faalde."""
    try:
        from app.database import SessionLocal
        from app.domains.mail.models import EmailLog

        db = SessionLocal()
        try:
            entry = EmailLog(
                recipient=to_email,
                subject=subject,
                body=body_html,
                email_type=email_type,
                status=status,
                error_message=error,
            )
            db.add(entry)
            db.commit()
            return entry.id
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - logging mag nooit de mail breken
        logger.error("E-maillog wegschrijven mislukt (%s): %s", subject, exc)
        return None


def _enqueue_retry(email_log_id: Optional[int]) -> None:
    """Plan een mail.retry-job (kernel-jobs, §5.8) voor een gefaalde verzending.
    Eigen sessie: _send draait meestal in een BackgroundTask zonder request-
    transactie. Falen mag de flow nooit breken — de log-rij blijft 'failed'."""
    if email_log_id is None:
        return
    try:
        from app.database import SessionLocal
        from app.kernel.jobs import enqueue

        db = SessionLocal()
        try:
            enqueue(db, "mail.retry", {"email_log_id": email_log_id})
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - vangnet
        logger.error("mail.retry-job plannen mislukt (log #%s): %s", email_log_id, exc)


def _display_name() -> str:
    """Merk-/afzendnaam van de actieve tenant (branding-slice #407) — default
    Raak Millegem. Mag het versturen nooit breken."""
    try:
        from app.database import SessionLocal
        from app.kernel.tenant_config import tenant_display_name

        db = SessionLocal()
        try:
            return tenant_display_name(db)
        finally:
            db.close()
    except Exception:
        return "Raak Millegem"


def _mail_mode() -> str:
    """Per-tenant mail-modus (fase 5b, #406): de demo-tenant logt mails enkel
    ("log_only") en verstuurt nooit echt. Fouten mogen versturen nooit breken."""
    try:
        from app.database import SessionLocal
        from app.kernel.tenant_config import tenant_mail_mode

        db = SessionLocal()
        try:
            return tenant_mail_mode(db)
        finally:
            db.close()
    except Exception:
        return "send"


def _gmail_config() -> tuple:
    """(gebruiker, app-wachtwoord, from) van de actieve tenant; .env als fallback.
    Mag het versturen nooit breken."""
    try:
        from app.database import SessionLocal
        from app.kernel.tenant_config import (
            tenant_gmail_app_password, tenant_gmail_from, tenant_gmail_user)

        db = SessionLocal()
        try:
            return (tenant_gmail_user(db), tenant_gmail_app_password(db),
                    tenant_gmail_from(db))
        finally:
            db.close()
    except Exception:
        return (settings.gmail_user, settings.gmail_app_password, settings.gmail_from)


def _payment_config() -> tuple:
    """(betaaltermijn-dagen, IBAN, begunstigde) van de actieve tenant; .env-fallback."""
    try:
        from app.database import SessionLocal
        from app.kernel.tenant_config import (
            tenant_payment_beneficiary, tenant_payment_iban, tenant_payment_term_days)

        db = SessionLocal()
        try:
            return (tenant_payment_term_days(db), tenant_payment_iban(db),
                    tenant_payment_beneficiary(db))
        finally:
            db.close()
    except Exception:
        return (settings.payment_term_days, settings.payment_iban,
                settings.payment_beneficiary)


def _send(to_email: str, subject: str, body_html: str, cc: Optional[str] = None, email_type: str = "other") -> None:
    if _mail_mode() == "log_only":
        _log_email(to_email, subject, body_html, email_type, "logged",
                   "demo-tenant: alleen gelogd, niet verstuurd")
        return
    gmail_user, gmail_password, gmail_from = _gmail_config()
    if not gmail_user or not gmail_password:
        logger.warning("E-mail niet verstuurd (GMAIL_USER of GMAIL_APP_PASSWORD niet ingesteld): %s", subject)
        _log_email(to_email, subject, body_html, email_type, "skipped", "GMAIL_USER/GMAIL_APP_PASSWORD niet ingesteld")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{_env_prefix()}{subject}"
    from_address = gmail_from or gmail_user
    msg["From"] = f"{_display_name()} <{from_address}>"
    msg["To"] = to_email
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body_html, "html"))

    recipients = [to_email] + ([cc] if cc else [])
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipients, msg.as_string())
    except Exception as exc:
        logger.error("E-mail versturen mislukt naar %s: %s", to_email, exc)
        log_id = _log_email(to_email, subject, body_html, email_type, "failed", str(exc))
        _enqueue_retry(log_id)
        return
    _log_email(to_email, subject, body_html, email_type, "sent", None)


def _transfer_instructions_html(payment_record) -> str:
    """Betaalinstructies-blok voor een overschrijving (#157): bedrag, IBAN,
    begunstigde, gestructureerde mededeling en betaaltermijn. Leeg voor andere
    betaalmethodes of wanneer de OGM ontbreekt."""
    if not payment_record or getattr(payment_record, "method", None) != "transfer":
        return ""
    ogm = getattr(payment_record, "structured_communication", None)
    if not ogm:
        return ""
    from datetime import date, timedelta
    term_days, iban, beneficiary = _payment_config()
    due = date.today() + timedelta(days=term_days)
    rows = [f"<li><strong>Bedrag:</strong> €{payment_record.amount:.2f}</li>"]
    if iban:
        rows.append(f"<li><strong>Rekeningnummer:</strong> {escape(iban)}</li>")
    if beneficiary:
        rows.append(f"<li><strong>Begunstigde:</strong> {escape(beneficiary)}</li>")
    rows.append(f"<li><strong>Gestructureerde mededeling:</strong> {escape(ogm)}</li>")
    rows.append(f"<li><strong>Te betalen vóór:</strong> {due.strftime('%d/%m/%Y')}</li>")
    return (
        _("<h4 style='margin-top:12px;margin-bottom:4px'>Betaalinstructies (overschrijving)</h4>"
          "<p>Schrijf het bedrag over met de gestructureerde mededeling hieronder, "
          "zodat we je betaling correct kunnen verwerken:</p>")
        + f"<ul>{''.join(rows)}</ul>"
    )


def send_magic_link(to_email: str, magic_link: str, otp_code: Optional[str] = None) -> None:
    otp_block = ""
    if otp_code:
        otp_block = f"""
        <p>Of voer deze code in op het apparaat waar je wil inloggen:</p>
        <p style="font-size:1.6em;font-weight:bold;letter-spacing:0.15em">{otp_code}</p>
        """
    _send(
        to_email=to_email,
        email_type="magic_link",
        subject=_("Inloglink %(naam)s") % {"naam": _display_name()},
        body_html=f"""
        <p>Klik op onderstaande link om in te loggen. De link is 15 minuten geldig.</p>
        <p><a href="{magic_link}">{magic_link}</a></p>
        {otp_block}
        <p>Als je deze mail niet verwachtte, kun je hem negeren.</p>
        <p>Met vriendelijke groeten,<br>{_display_name()}</p>
        """,
    )


def send_member_contact_board_notice(to_email: str) -> None:
    """Wanneer een e-mailadres aan meerdere gezinnen hangt, kunnen we niet
    veilig bepalen op welk gezin in te loggen. We sturen geen inloglink maar
    vragen contact op te nemen met het bestuur."""
    _send(
        to_email=to_email,
        email_type="member_contact_notice",
        subject=_("Inloggen %(naam)s") % {"naam": _display_name()},
        body_html=_("""
        <p>Je probeerde in te loggen als lid, maar dit e-mailadres is bij meerdere
        gezinnen gekend. Daardoor kunnen we niet automatisch bepalen welk gezin
        je wil beheren.</p>
        <p>Neem contact op met het bestuur, dan zetten we dit recht.</p>
        <p>Met vriendelijke groeten,<br>%(naam)s</p>
        """) % {"naam": _display_name()},
    )


def send_registration_confirmation(to_email: str, name: str, family, data=None, pc_municipality: str = "", background_tasks=None, payment_record=None) -> None:
    details = ""
    if data:
        address_parts = [data.street, data.house_number]
        if data.bus_number:
            address_parts.append(f"bus {data.bus_number}")
        address_line = " ".join(str(p) for p in address_parts)
        postal_line = f"{data.postal_code} {pc_municipality}".strip()

        members_html = ""
        for m in data.members:
            member_name = escape(f"{m.first_name} {m.last_name}")
            parts = [f"<strong>{member_name}</strong> ({escape(m.relation_type)})"]
            if m.date_of_birth:
                parts.append(str(m.date_of_birth.strftime("%d/%m/%Y") if hasattr(m.date_of_birth, "strftime") else m.date_of_birth))
            if m.email:
                parts.append(escape(m.email))
            if m.phone:
                parts.append(escape(m.phone))
            if m.mobile:
                parts.append(escape(m.mobile))
            members_html += f"<li>{' — '.join(parts)}</li>"

        method_labels = {"online": _("Online (Mollie)"), "cash": _("Cash"), "transfer": _("Overschrijving")}
        payment_label = method_labels.get(data.payment_method, data.payment_method)

        details = f"""
        <h4 style='margin-top:12px;margin-bottom:4px'>Adres</h4>
        <p>{escape(address_line)}<br>{escape(postal_line)}</p>
        <h4 style='margin-top:12px;margin-bottom:4px'>Gezinsleden</h4>
        <ul>{members_html}</ul>
        <h4 style='margin-top:12px;margin-bottom:4px'>Betaling</h4>
        <p>{payment_label}</p>
        """

    _dispatch(
        background_tasks,
        to_email=to_email,
        email_type="membership_confirmation",
        subject=_("Welkom bij %(naam)s!") % {"naam": _display_name()},
        cc=settings.gmail_from or settings.gmail_user or None,
        body_html=f"""
        <p>Beste {escape(name)},</p>
        <p>Je registratie bij {_display_name()} is ontvangen. Welkom!</p>
        {details}
        {_transfer_instructions_html(payment_record)}
        <p>Met vriendelijke groeten,<br>{_display_name()}</p>
        """,
    )


def send_activity_registration_confirmation(
    to_email: str, name: str, activity, registration=None, background_tasks=None, payment_record=None
) -> None:
    activity_name = escape(activity.name)
    subject = _("Inschrijving bevestigd: %(name)s") % {"name": activity_name}
    from datetime import date as _date
    today = _date.today()
    all_dates = sorted(activity.dates, key=lambda d: d.start_date) if activity.dates else []
    relevant = next((d for d in all_dates if (d.end_date or d.start_date) >= today), all_dates[0] if all_dates else None)
    date_str = relevant.start_date.strftime("%d/%m/%Y") if relevant else ""
    time_str = relevant.start_time.strftime("%H:%M") if (relevant and relevant.start_time) else ""
    location = escape(activity.location) if activity.location else ""

    loc_li = f"<li><strong>Locatie:</strong> {location}</li>" if location else ""
    time_li = f"<li><strong>Tijdstip:</strong> {time_str}</li>" if time_str else ""
    message = (
        f"<p>Je inschrijving voor <strong>{activity_name}</strong> is bevestigd.</p>"
        f"<ul><li><strong>Datum:</strong> {date_str}</li>{time_li}{loc_li}</ul>"
    )

    if registration:
        details = []
        if registration.contact_email:
            details.append(f"<li><strong>E-mail:</strong> {escape(registration.contact_email)}</li>")
        if registration.phone:
            details.append(f"<li><strong>GSM:</strong> {escape(registration.phone)}</li>")
        if registration.team_name:
            details.append(f"<li><strong>Ploeg:</strong> {escape(registration.team_name)}</li>")
        if registration.remarks:
            details.append(f"<li><strong>Opmerkingen:</strong> {escape(registration.remarks)}</li>")

        totaal, regels = compute_registration_total(registration)
        if regels:
            def _regel_html(r):
                naam = f"{escape(r['name'])} × {r['quantity']}"
                if r.get("pay_on_site"):
                    # Eigen budget: geen bedrag, wel duidelijk dat het ter plaatse is (#373).
                    return f"<li>{naam} — ter plaatse te betalen (eigen budget)</li>"
                if r.get("is_free"):
                    return f"<li>{naam} — gratis</li>"
                return (
                    f"<li>{naam} — €{r['unit_price']:.2f} / stuk "
                    f"= <strong>€{r['subtotal']:.2f}</strong></li>"
                )
            regels_html = "".join(_regel_html(r) for r in regels)
            details.append(f"<li><strong>Producten:</strong><ul>{regels_html}</ul></li>")
            if totaal > 0:
                details.append(f"<li><strong>Totaal:</strong> <strong>€{totaal:.2f}</strong></li>")

        if registration.payment_method and registration.payment_method != "FREE":
            method_labels = {"ONLINE": _("Online (Mollie)"), "CASH": _("Cash"), "TRANSFER": _("Overschrijving")}
            details.append(
                f"<li><strong>Betaalmethode:</strong> "
                f"{method_labels.get(registration.payment_method, registration.payment_method)}</li>"
            )

        if details:
            message += (
                "<h4 style='margin-top:12px;margin-bottom:4px'>Jouw gegevens</h4>"
                f"<ul>{''.join(details)}</ul>"
            )

    message += _transfer_instructions_html(payment_record)

    _dispatch(
        background_tasks,
        to_email=to_email,
        email_type="activity_confirmation",
        subject=subject,
        body_html=f"<p>Beste {escape(name)},</p>{message}<p>Met vriendelijke groeten,<br>{_display_name()}</p>",
    )


def send_form_confirmation(
    to_email: str,
    form_title: str,
    name: Optional[str] = None,
    confirmation_message: Optional[str] = None,
    edit_link: Optional[str] = None,
    background_tasks=None,
) -> None:
    """Bevestiging na het indienen van een formulier (#327). Optioneel een
    wijzig-link als het formulier dat toelaat."""
    greeting = _("<p>Beste %(name)s,</p>") % {"name": escape(name)} if name else _("<p>Beste,</p>")
    custom = f"<p>{escape(confirmation_message)}</p>" if confirmation_message else ""
    edit_block = ""
    if edit_link:
        edit_block = (
            _("<p>Je kan je antwoord later nog aanpassen via deze link "
              "(zolang het formulier open staat):</p>")
            + f'<p><a href="{edit_link}">{edit_link}</a></p>'
        )
    _dispatch(
        background_tasks,
        to_email=to_email,
        email_type="form_confirmation",
        subject=_("Bevestiging: %(title)s") % {"title": escape(form_title)},
        body_html=(
            f"{greeting}"
            f"<p>We hebben je antwoord op <strong>{escape(form_title)}</strong> goed ontvangen.</p>"
            f"{custom}{edit_block}"
            f"<p>Met vriendelijke groeten,<br>{_display_name()}</p>"
        ),
    )




def purge_old_email_logs(db, retention_days: Optional[int] = None) -> int:
    """Verwijder email_log-rijen ouder dan de bewaartermijn (#328). Geeft het
    aantal verwijderde rijen terug. retention_days <= 0 (of None met default <= 0)
    = niets verwijderen (oneindig bewaren)."""
    from datetime import datetime, timezone, timedelta

    from app.domains.mail.models import EmailLog

    days = settings.email_log_retention_days if retention_days is None else retention_days
    if not days or days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = (
        db.query(EmailLog)
        .filter(EmailLog.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
