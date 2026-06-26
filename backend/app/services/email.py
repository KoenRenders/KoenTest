import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Optional

from app.config import settings
from app.services.registration_totals import compute_registration_total

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


def _log_email(to_email: str, subject: str, body_html: str, email_type: str, status: str, error: Optional[str]) -> None:
    """Schrijf één rij naar de centrale email_log (#328). Loggen mag het versturen
    nooit breken: alle fouten worden hier opgevangen. Gebruikt een eigen
    SessionLocal omdat _send vaak in een BackgroundTask draait (geen request-sessie)."""
    try:
        from app.database import SessionLocal
        from app.models.email_log import EmailLog

        db = SessionLocal()
        try:
            db.add(EmailLog(
                recipient=to_email,
                subject=subject,
                body=body_html,
                email_type=email_type,
                status=status,
                error_message=error,
            ))
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - logging mag nooit de mail breken
        logger.error("E-maillog wegschrijven mislukt (%s): %s", subject, exc)


def _send(to_email: str, subject: str, body_html: str, cc: Optional[str] = None, email_type: str = "other") -> None:
    if not settings.gmail_user or not settings.gmail_app_password:
        logger.warning("E-mail niet verstuurd (GMAIL_USER of GMAIL_APP_PASSWORD niet ingesteld): %s", subject)
        _log_email(to_email, subject, body_html, email_type, "skipped", "GMAIL_USER/GMAIL_APP_PASSWORD niet ingesteld")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{_env_prefix()}{subject}"
    from_address = settings.gmail_from or settings.gmail_user
    msg["From"] = f"Raak Millegem <{from_address}>"
    msg["To"] = to_email
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body_html, "html"))

    recipients = [to_email] + ([cc] if cc else [])
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(settings.gmail_user, settings.gmail_app_password)
            server.sendmail(settings.gmail_user, recipients, msg.as_string())
    except Exception as exc:
        logger.error("E-mail versturen mislukt naar %s: %s", to_email, exc)
        _log_email(to_email, subject, body_html, email_type, "failed", str(exc))
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
    due = date.today() + timedelta(days=settings.payment_term_days)
    rows = [f"<li><strong>Bedrag:</strong> €{payment_record.amount:.2f}</li>"]
    if settings.payment_iban:
        rows.append(f"<li><strong>Rekeningnummer:</strong> {escape(settings.payment_iban)}</li>")
    if settings.payment_beneficiary:
        rows.append(f"<li><strong>Begunstigde:</strong> {escape(settings.payment_beneficiary)}</li>")
    rows.append(f"<li><strong>Gestructureerde mededeling:</strong> {escape(ogm)}</li>")
    rows.append(f"<li><strong>Te betalen vóór:</strong> {due.strftime('%d/%m/%Y')}</li>")
    return (
        "<h4 style='margin-top:12px;margin-bottom:4px'>Betaalinstructies (overschrijving)</h4>"
        "<p>Schrijf het bedrag over met de gestructureerde mededeling hieronder, "
        "zodat we je betaling correct kunnen verwerken:</p>"
        f"<ul>{''.join(rows)}</ul>"
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
        subject="Inloglink Raak Millegem",
        body_html=f"""
        <p>Klik op onderstaande link om in te loggen. De link is 15 minuten geldig.</p>
        <p><a href="{magic_link}">{magic_link}</a></p>
        {otp_block}
        <p>Als je deze mail niet verwachtte, kun je hem negeren.</p>
        <p>Met vriendelijke groeten,<br>Raak Millegem</p>
        """,
    )


def send_member_contact_board_notice(to_email: str) -> None:
    """Wanneer een e-mailadres aan meerdere gezinnen hangt, kunnen we niet
    veilig bepalen op welk gezin in te loggen. We sturen geen inloglink maar
    vragen contact op te nemen met het bestuur."""
    _send(
        to_email=to_email,
        email_type="member_contact_notice",
        subject="Inloggen Raak Millegem",
        body_html="""
        <p>Je probeerde in te loggen als lid, maar dit e-mailadres is bij meerdere
        gezinnen gekend. Daardoor kunnen we niet automatisch bepalen welk gezin
        je wil beheren.</p>
        <p>Neem contact op met het bestuur, dan zetten we dit recht.</p>
        <p>Met vriendelijke groeten,<br>Raak Millegem</p>
        """,
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

        method_labels = {"online": "Online (Mollie)", "cash": "Cash", "transfer": "Overschrijving"}
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
        subject="Welkom bij Raak Millegem!",
        cc=settings.gmail_from or settings.gmail_user or None,
        body_html=f"""
        <p>Beste {escape(name)},</p>
        <p>Je registratie bij Raak Millegem is ontvangen. Welkom!</p>
        {details}
        {_transfer_instructions_html(payment_record)}
        <p>Met vriendelijke groeten,<br>Raak Millegem</p>
        """,
    )


def send_activity_registration_confirmation(
    to_email: str, name: str, activity, registration=None, background_tasks=None, payment_record=None
) -> None:
    activity_name = escape(activity.name)
    subject = f"Inschrijving bevestigd: {activity_name}"
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
            regels_html = "".join(
                f"<li>{escape(r['name'])} × {r['quantity']} "
                f"— €{r['unit_price']:.2f} / stuk "
                f"= <strong>€{r['subtotal']:.2f}</strong></li>"
                for r in regels
            )
            details.append(f"<li><strong>Producten:</strong><ul>{regels_html}</ul></li>")
            details.append(f"<li><strong>Totaal:</strong> <strong>€{totaal:.2f}</strong></li>")

        if registration.payment_method and registration.payment_method != "FREE":
            method_labels = {"ONLINE": "Online (Mollie)", "CASH": "Cash", "TRANSFER": "Overschrijving"}
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
        body_html=f"<p>Beste {escape(name)},</p>{message}<p>Met vriendelijke groeten,<br>Raak Millegem</p>",
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
    greeting = f"<p>Beste {escape(name)},</p>" if name else "<p>Beste,</p>"
    custom = f"<p>{escape(confirmation_message)}</p>" if confirmation_message else ""
    edit_block = ""
    if edit_link:
        edit_block = (
            "<p>Je kan je antwoord later nog aanpassen via deze link "
            "(zolang het formulier open staat):</p>"
            f'<p><a href="{edit_link}">{edit_link}</a></p>'
        )
    _dispatch(
        background_tasks,
        to_email=to_email,
        email_type="form_confirmation",
        subject=f"Bevestiging: {escape(form_title)}",
        body_html=(
            f"{greeting}"
            f"<p>We hebben je antwoord op <strong>{escape(form_title)}</strong> goed ontvangen.</p>"
            f"{custom}{edit_block}"
            "<p>Met vriendelijke groeten,<br>Raak Millegem</p>"
        ),
    )


def send_idea_acknowledgement(to_email: str, name: str, message: str) -> None:
    _send(
        to_email=to_email,
        email_type="idea_ack",
        subject="Idee ontvangen – Raak Millegem",
        body_html=f"""
        <p>Beste {escape(name)},</p>
        <p>Bedankt voor je idee! We bekijken het zo snel mogelijk.</p>
        <blockquote style="border-left:4px solid #ccc;padding-left:12px;color:#555;">{escape(message)}</blockquote>
        <p>Met vriendelijke groeten,<br>Raak Millegem</p>
        """,
    )


def send_idea_board_notification(name: str, email: Optional[str], message: str) -> None:
    """Verwittig het bestuur (GMAIL_FROM) bij een nieuw bericht via het
    contactformulier/de chatbot (#260), zodat het niet onopgemerkt in de IdeaBox
    blijft staan. Stuurt enkel als er een bestuursadres geconfigureerd is."""
    board = settings.gmail_from or settings.gmail_user
    if not board:
        return
    _send(
        to_email=board,
        email_type="idea_board",
        subject="Nieuw bericht via het contactformulier – Raak Millegem",
        body_html=f"""
        <p>Er kwam een nieuw bericht binnen via het contactformulier:</p>
        <p><strong>Naam:</strong> {escape(name or "—")}<br>
        <strong>E-mail:</strong> {escape(email or "niet opgegeven")}</p>
        <blockquote style="border-left:4px solid #ccc;padding-left:12px;color:#555;">{escape(message)}</blockquote>
        """,
    )


def purge_old_email_logs(db, retention_days: Optional[int] = None) -> int:
    """Verwijder email_log-rijen ouder dan de bewaartermijn (#328). Geeft het
    aantal verwijderde rijen terug. retention_days <= 0 (of None met default <= 0)
    = niets verwijderen (oneindig bewaren)."""
    from datetime import datetime, timezone, timedelta

    from app.models.email_log import EmailLog

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
