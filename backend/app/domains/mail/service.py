import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Optional

from app.config import settings
from app.domains.activities.api import compute_registration_total
from app.domains.mail.models import MailStatus
from app.i18n import _
from app.kernel.codes import code_label
from app.kernel.phone import readable_phone
from app.kernel.rules import own_transaction

logger = logging.getLogger(__name__)


def _env_prefix() -> str:
    env = (settings.app_env or "").lower()
    if env in ("dev", "hdev", "uat"):
        return f"[{env.upper()}] "
    return ""


def email_log_url(db, log_id) -> str | None:
    """Where can this log line be viewed? (#822)

    The e-mail log filters on recipient rather than on id, so this looks up the address
    and filters on that. It shows the mail AND its earlier attempts — which is exactly
    what you want to see for a mail that failed for good.

    The URL lives HERE and not in the workbench: this domain owns that screen and its
    route shape. A task should not have to know what an e-mail-log URL looks like.
    """
    from urllib.parse import quote

    from app.domains.mail.models import EmailLog

    try:
        log = db.get(EmailLog, int(log_id))
    except (TypeError, ValueError):
        return None
    if log is None or not log.recipient:
        return None
    return f"/admin/e-maillog?recipient={quote(log.recipient)}"


#: The job that sends one finished message (CR-13 phase 4). Its payload is the
#: message itself and is emptied once sent (`kernel.jobs`, `scrub_payload`).
SEND_JOB = "mail.send"


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


def queue_mail(
    db,
    to_email: str,
    subject: str,
    body_html: str,
    cc: Optional[str] = None,
    email_type: str = "other",
) -> None:
    """Queue one finished message as a job in `db`'s transaction (CR-13 phase 4,
    §B4.1): it leaves only if that transaction commits, and whoever queues it never
    reaches the network — the `mail.send` job does, through `_send`."""
    from app.kernel.jobs import enqueue

    enqueue(
        db,
        SEND_JOB,
        {
            "to_email": to_email,
            "subject": subject,
            "body_html": body_html,
            "cc": cc,
            "email_type": email_type,
        },
    )


@own_transaction(
    "mail.email_log", "a sent mail stays logged when the request that sent it fails (#328)"
)
def _log_email(
    to_email: str,
    subject: str,
    body_html: str,
    email_type: str,
    status: MailStatus,
    error: Optional[str],
) -> Optional[int]:
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


@own_transaction("kernel_jobs", "the retry of a failed mail outlives the request that failed it")
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
            tenant_gmail_app_password,
            tenant_gmail_from,
            tenant_gmail_user,
        )

        db = SessionLocal()
        try:
            return (tenant_gmail_user(db), tenant_gmail_app_password(db), tenant_gmail_from(db))
        finally:
            db.close()
    except Exception:
        return (settings.gmail_user, settings.gmail_app_password, settings.gmail_from)


def _send(
    to_email: str, subject: str, body_html: str, cc: Optional[str] = None, email_type: str = "other"
) -> None:
    if _mail_mode() == "log_only":
        _log_email(
            to_email,
            subject,
            body_html,
            email_type,
            MailStatus.LOGGED,
            "demo-tenant: alleen gelogd, niet verstuurd",
        )
        return
    gmail_user, gmail_password, gmail_from = _gmail_config()
    if not gmail_user or not gmail_password:
        logger.warning(
            "E-mail niet verstuurd (GMAIL_USER of GMAIL_APP_PASSWORD niet ingesteld): %s", subject
        )
        _log_email(
            to_email,
            subject,
            body_html,
            email_type,
            MailStatus.SKIPPED,
            "GMAIL_USER/GMAIL_APP_PASSWORD niet ingesteld",
        )
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
        log_id = _log_email(to_email, subject, body_html, email_type, MailStatus.FAILED, str(exc))
        _enqueue_retry(log_id)
        return
    _log_email(to_email, subject, body_html, email_type, MailStatus.SENT, None)


class SendingQuotaReached(RuntimeError):
    """Gmail refused because the account's daily sending quota is used up.

    Not a failure of this mail: the same mail goes through tomorrow. The caller
    pauses its queue instead of marking anything as failed (CR-05 §3.7).
    """


# Gmail answers a used-up daily quota with an extended status 5.4.5 ("Daily user
# sending limit exceeded"). Matched loosely, because the wording is Google's and
# changes; the code is the stable part.
_QUOTA_MARKERS = ("5.4.5", "sending limit exceeded", "sending quota")


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _QUOTA_MARKERS)


def send_campaign_mail(
    to_email: str,
    subject: str,
    body_html: str,
    *,
    email_type: str,
    reply_to: Optional[str] = None,
    unsubscribe_url: Optional[str] = None,
    body_text: Optional[str] = None,
) -> str:
    """One mail to one recipient, for a campaign such as the newsletter (#984).

    Differs from ``_send`` on three points, each a decision:

    - **No retry job.** The campaign keeps its own queue row per recipient; a
      second, independent retry mechanism could send the same letter twice.
      The outcome is returned, and the caller records it.
    - **A used-up Gmail quota raises** ``SendingQuotaReached`` instead of being
      logged as a failure: the mail is fine, the day is full.
    - **Unsubscribe headers** when ``unsubscribe_url`` is given: a
      ``List-Unsubscribe`` header plus ``List-Unsubscribe-Post`` for one-click
      unsubscribing from the mail client (RFC 8058).
    - **A text part** when ``body_text`` is given (#984). The message announces
      itself as ``multipart/alternative``, so without it a reader that strips
      HTML — a screen reader, a watch, a client set to plain text — is left with
      a blank page. The text part goes FIRST: the last part is the preferred
      one, and that must stay the HTML.

    Returns the log status: ``sent``, ``logged`` (demo tenant), ``skipped`` (no
    credentials) or ``failed``.
    """
    if _mail_mode() == "log_only":
        _log_email(
            to_email,
            subject,
            body_html,
            email_type,
            MailStatus.LOGGED,
            "demo-tenant: alleen gelogd, niet verstuurd",
        )
        return "logged"
    gmail_user, gmail_password, gmail_from = _gmail_config()
    if not gmail_user or not gmail_password:
        _log_email(
            to_email,
            subject,
            body_html,
            email_type,
            MailStatus.SKIPPED,
            "GMAIL_USER/GMAIL_APP_PASSWORD niet ingesteld",
        )
        return "skipped"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{_env_prefix()}{subject}"
    msg["From"] = f"{_display_name()} <{gmail_from or gmail_user}>"
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    if unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    # The text part goes FIRST: in `multipart/alternative` the LAST part is the
    # preferred one, and that must stay the HTML.
    if body_text:
        msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, [to_email], msg.as_string())
    except Exception as exc:
        if _is_quota_error(exc):
            logger.warning("Gmail-dagquotum bereikt bij %s: %s", to_email, exc)
            raise SendingQuotaReached(str(exc)) from exc
        logger.error("Campagnemail naar %s mislukt: %s", to_email, exc)
        _log_email(to_email, subject, body_html, email_type, MailStatus.FAILED, str(exc))
        return "failed"
    _log_email(to_email, subject, body_html, email_type, MailStatus.SENT, None)
    return "sent"


def send_newsletter_confirmation(to_email: str, first_name: Optional[str], confirm_url: str) -> str:
    """The double opt-in mail (CR-05 §3.5): one button, and what to do if it
    was not you. Nothing is sent to this address until the button is used."""
    greeting = (_("Dag %(naam)s,") % {"naam": escape(first_name)}) if first_name else _("Dag,")
    body = f"""
        <p>{greeting}</p>
        <p>{_("Iemand — hopelijk jij — schreef dit adres in voor de nieuwsbrief van %(naam)s.") % {"naam": escape(_display_name())}}</p>
        <p><a href="{escape(confirm_url)}" style="display:inline-block;padding:10px 18px;background:#0051a4;color:#ffffff;border-radius:8px;text-decoration:none;font-weight:600">{_("Ja, ik wil de nieuwsbrief")}</a></p>
        <p style="color:#52607a;font-size:13px">{_("Was jij het niet? Dan hoef je niets te doen: zonder bevestiging sturen we niets.")}</p>
    """
    return send_campaign_mail(
        to_email,
        _("Bevestig je inschrijving op de nieuwsbrief"),
        body,
        email_type="newsletter_confirmation",
    )


def _transfer_instructions_html(transfer) -> str:
    """The transfer block of a confirmation mail (#157). `transfer` is payment's
    `TransferDue` — the lines, their words and their values are the ones the
    screens show (#1775) — or None for a payment that is not a transfer."""
    if transfer is None:
        return ""
    rows = "".join(
        f"<li><strong>{escape(line.label)}:</strong> {escape(line.value)}</li>"
        for line in transfer.lines
    )
    return (
        f"<h4 style='margin-top:12px;margin-bottom:4px'>{escape(transfer.heading)}</h4>"
        + _(
            "<p>Schrijf het bedrag over met de gestructureerde mededeling hieronder, "
            "zodat we je betaling correct kunnen verwerken:</p>"
        )
        + f"<ul>{rows}</ul>"
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


def code_mail_message(kind: str, link: str, otp_code: str) -> tuple[str, str]:
    """`(subject, body)` of a mail that carries a link AND a code for the same
    token — either does it (CR-22 Q36), as the sign-in mail above does.

    `kind` is `ADDRESS_CONFIRMATION`, `ACCOUNT_CONFIRMATION` or
    `EXISTING_ACCOUNT` of `kernel.contracts.auth`; the words that differ are
    here, the body is one.
    """
    from app.kernel.contracts.auth import (
        ACCOUNT_CONFIRMATION,
        ADDRESS_CONFIRMATION,
        EXISTING_ACCOUNT,
    )

    name = _display_name()
    if kind == ADDRESS_CONFIRMATION:
        # "Bevestig je e-mailadres" (R15, #1711): an address somebody typed in
        # Mijn gezin or Mijn gegevens counts once the link or the code is used.
        subject = _("Bevestig je e-mailadres bij %(naam)s") % {"naam": name}
        lead = _(
            "Dit e-mailadres werd toegevoegd bij %(naam)s. Klik op onderstaande link "
            "om het te bevestigen."
        ) % {"naam": name}
    elif kind == ACCOUNT_CONFIRMATION:
        # "Bevestig je account" (R3): the account exists once the link or the
        # code is used — not before.
        subject = _("Bevestig je account bij %(naam)s") % {"naam": name}
        lead = _("Klik op onderstaande link om je account bij %(naam)s te bevestigen.") % {
            "naam": name
        }
    elif kind == EXISTING_ACCOUNT:
        # "Je hebt al een account" (R4): the SCREEN said the same as for a new
        # address; only this mail, to the owner, says it exists.
        subject = _("Je hebt al een account bij %(naam)s") % {"naam": name}
        lead = _(
            "Er werd een account aangevraagd met dit e-mailadres, maar je hebt er al een "
            "bij %(naam)s. Klik op onderstaande link om in te loggen."
        ) % {"naam": name}
    else:
        raise ValueError(f"Unknown kind of code mail: {kind}")
    body = f"""
        <p>{escape(lead)}</p>
        <p><a href="{link}">{link}</a></p>
        <p>{escape(_("Of voer deze code in op het apparaat waar je bezig was:"))}</p>
        <p style="font-size:1.6em;font-weight:bold;letter-spacing:0.15em">{otp_code}</p>
        <p>{escape(_("De link en de code zijn 15 minuten geldig. Als je deze mail niet verwachtte, kun je hem negeren."))}</p>
        <p>{escape(_("Met vriendelijke groeten,"))}<br>{escape(name)}</p>
        """
    return subject, body


def member_contact_board_notice_message() -> tuple[str, str]:
    """`(subject, body)` of the notice below — for whoever queues it instead of
    sending it (the account request, CR-22). One text, two ways out."""
    return (
        _("Inloggen %(naam)s") % {"naam": _display_name()},
        _board_notice_body() % {"naam": _display_name()},
    )


def _board_notice_body() -> str:
    """The notice's text; a function, because it translates per request.

    One text for every address that does not say who signs in (#1740): two
    households, two persons without one, or one of each. Until then it said
    "bij meerdere gezinnen gekend", wrong for the last two."""
    return _("""
        <p>Je probeerde in te loggen, maar dit e-mailadres is bij meer dan één
        persoon gekend. Daardoor kunnen we niet bepalen wie je bent.</p>
        <p>Neem contact op met het bestuur, dan zetten we dit recht.</p>
        <p>Met vriendelijke groeten,<br>%(naam)s</p>
        """)


def send_member_contact_board_notice(to_email: str) -> None:
    """Wanneer een e-mailadres aan meerdere gezinnen hangt, kunnen we niet
    veilig bepalen op welk gezin in te loggen. We sturen geen inloglink maar
    vragen contact op te nemen met het bestuur."""
    subject, body = member_contact_board_notice_message()
    _send(to_email=to_email, email_type="member_contact_notice", subject=subject, body_html=body)


def family_welcome_message(
    to_email: str,
    name: str,
    data=None,
    pc_municipality: str = "",
    transfer=None,
) -> dict:
    """The welcome mail of a household that registered itself, as a finished message
    for `queue_mail` (CR-13 phase 4: built in the request, sent by a job)."""
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
            # `.value`: since CR-12 phase 2 (v2.7.0) the form carries a `RelationType`
            # member, and `escape` on a member failed — so the welcome mail was never
            # sent (found in CR-13 phase 4). The stored code, as the mail showed it
            # up to v2.6.0.
            parts = [f"<strong>{member_name}</strong> ({escape(m.relation_type.value)})"]
            if m.date_of_birth:
                parts.append(
                    str(
                        m.date_of_birth.strftime("%d/%m/%Y")
                        if hasattr(m.date_of_birth, "strftime")
                        else m.date_of_birth
                    )
                )
            if m.email:
                parts.append(escape(m.email))
            if m.phone:
                parts.append(escape(readable_phone(m.phone)))
            if m.mobile:
                parts.append(escape(readable_phone(m.mobile)))
            members_html += f"<li>{' — '.join(parts)}</li>"

        method_labels = {
            "online": _("Online (Mollie)"),
            "cash": _("Cash"),
            "transfer": _("Overschrijving"),
        }
        payment_label = method_labels.get(data.payment_method, data.payment_method)

        details = f"""
        <h4 style='margin-top:12px;margin-bottom:4px'>Adres</h4>
        <p>{escape(address_line)}<br>{escape(postal_line)}</p>
        <h4 style='margin-top:12px;margin-bottom:4px'>Gezinsleden</h4>
        <ul>{members_html}</ul>
        <h4 style='margin-top:12px;margin-bottom:4px'>Betaling</h4>
        <p>{payment_label}</p>
        """

    return dict(
        to_email=to_email,
        email_type="membership_confirmation",
        subject=_("Welkom bij %(naam)s!") % {"naam": _display_name()},
        cc=settings.gmail_from or settings.gmail_user or None,
        body_html=f"""
        <p>Beste {escape(name)},</p>
        <p>Je registratie bij {_display_name()} is ontvangen. Welkom!</p>
        {details}
        {_transfer_instructions_html(transfer)}
        <p>Met vriendelijke groeten,<br>{_display_name()}</p>
        """,
    )


def activity_confirmation_message(
    to_email: str,
    name: str,
    activity,
    registration=None,
    transfer=None,
    answer_url=None,
    answers=None,
    subject=None,
    history_url=None,
) -> dict:
    """The confirmation of an activity registration, as a finished message for
    `queue_mail` (CR-13 phase 4: built in the request, sent by a job).

    `history_url` (CR-22 R6, #1707): where a registration made while signed in
    stands afterwards — Mijn inschrijvingen. Only for a registration with a
    person; a guest has no account, so nothing to look up, and gets no link:
    the mail itself says what was registered.

    `answer_url` (CR-14 §B4.8): the registration chose to answer the component's
    questions later — the one mail carries the link, after the products and the
    payment information. `answers` (CR-14 R6, phase 3): the answers as (label,
    value), in the same place — the member's own words back to the member. One of
    the two, or neither when the component asks nothing. `subject` replaces the
    confirmation's subject — the reminder of the answer link."""
    activity_name = escape(activity.name)
    subject = subject or _("Inschrijving bevestigd: %(name)s") % {"name": activity_name}
    from datetime import date as _date

    today = _date.today()
    all_dates = sorted(activity.dates, key=lambda d: d.start_date) if activity.dates else []
    relevant = next(
        (d for d in all_dates if (d.end_date or d.start_date) >= today),
        all_dates[0] if all_dates else None,
    )
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
            details.append(
                f"<li><strong>E-mail:</strong> {escape(registration.contact_email)}</li>"
            )
        if registration.phone:
            details.append(
                f"<li><strong>Mobiel:</strong> {escape(readable_phone(registration.phone))}</li>"
            )
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

        if registration.payment_method:
            # CR-12 phase 1. The old branch compared against "FREE", a value
            # that has never been in this column: the codes are
            # online/transfer/cash and a free registration has NULL. An empty
            # value now drops out at the `if`, which does the same and is
            # actually true.
            #
            # No explicit language (§F12), and that is fine here: this message
            # is built INSIDE the registration request, so `current_locale` is
            # set to the language of the branch. Only when a job calls this
            # function does the language have to be passed along — then there
            # is no request and the locale falls back to nl_BE without anything
            # complaining.
            details.append(
                f"<li><strong>Betaalmethode:</strong> "
                f"{code_label('payment_method', registration.payment_method)}</li>"
            )

        if details:
            message += (
                "<h4 style='margin-top:12px;margin-bottom:4px'>Jouw gegevens</h4>"
                f"<ul>{''.join(details)}</ul>"
            )

    message += _transfer_instructions_html(transfer)

    if answers:
        rows = "".join(
            f"<li><strong>{escape(label)}:</strong> {escape(value) if value else '—'}</li>"
            for label, value in answers
        )
        message += (
            "<h4 style='margin-top:12px;margin-bottom:4px'>"
            + _("Jouw antwoorden")
            + f"</h4><ul>{rows}</ul>"
        )
    elif answer_url:
        message += (
            "<h4 style='margin-top:12px;margin-bottom:4px'>"
            + _("Nog even de vragen")
            + "</h4><p>"
            + _(
                "De organisatie stelt nog enkele vragen bij je inschrijving. Beantwoord ze via deze link:"
            )
            + f'</p><p><a href="{escape(answer_url)}">{escape(answer_url)}</a></p>'
        )

    if history_url:
        message += (
            "<p style='margin-top:12px'>"
            + _("Je vindt deze inschrijving terug onder Mijn inschrijvingen:")
            + f' <a href="{escape(history_url)}">{escape(history_url)}</a></p>'
        )

    return dict(
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
            _(
                "<p>Je kan je antwoord later nog aanpassen via deze link "
                "(zolang het formulier open staat):</p>"
            )
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
    from datetime import datetime, timedelta, timezone

    from app.domains.mail.models import EmailLog

    days = settings.email_log_retention_days if retention_days is None else retention_days
    if not days or days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = (
        db.query(EmailLog).filter(EmailLog.created_at < cutoff).delete(synchronize_session=False)
    )
    db.commit()
    return deleted


# ── E-maillogboek (#635 I) ───────────────────────────────────────────────────

# Sorteerbare kolommen (Ontwerpspoor golf 3, #913): sleutel → kolom. Een
# whitelist, geen vrije kolomnaam — dezelfde reden als "no free SQL, ever".
_EMAIL_LOG_SORT = {
    "datum": "created_at",
    "ontvanger": "recipient",
    "onderwerp": "subject",
    "type": "email_type",
    "status": "status",
}

#: De sleutels die een scherm mag aanbieden — via de facade, zodat de ui-laag
#: geen service-internals hoeft te kennen.
EMAIL_LOG_SORT_KEYS: tuple[str, ...] = tuple(_EMAIL_LOG_SORT)


def list_email_log(
    db,
    *,
    email_type: str = "",
    status: str = "",
    recipient: str = "",
    page: int = 1,
    page_size: int = 25,
    sort: str = "datum",
    richting: str = "desc",
):
    """Een pagina uit het e-maillogboek, met de actieve filters toegepast.

    Returns `(rows, total)`: the page and the number of rows that match the
    filters. The total is counted (#1391, CR-11 W8) — the pager says "x–y van n"
    everywhere, and "one row extra" could only say "page n".

    `sort` komt uit `_EMAIL_LOG_SORT` (onbekend → datum), `richting` is asc/desc
    (anders desc). Elke ordening eindigt op het unieke id in dezelfde richting —
    de #761-les: zonder tiebreaker toont paging dezelfde rij twee keer en een
    andere nooit.
    """
    from app.domains.mail.models import EmailLog

    query = db.query(EmailLog)
    if email_type:
        query = query.filter(EmailLog.email_type == email_type)
    if status:
        query = query.filter(EmailLog.status == status)
    if recipient:
        query = query.filter(EmailLog.recipient.ilike(f"%{recipient}%"))

    kolomnaam = _EMAIL_LOG_SORT.get(sort, "created_at")
    kolom = getattr(EmailLog, kolomnaam)
    aflopend = richting != "asc"
    orden = (kolom.desc(), EmailLog.id.desc()) if aflopend else (kolom.asc(), EmailLog.id.asc())

    total = query.order_by(None).count()
    rijen = query.order_by(*orden).offset((max(1, page) - 1) * page_size).limit(page_size).all()
    return rijen, total


def delete_email_log(db, log_id: int) -> bool:
    """Verwijder één logregel. Geeft terug of er iets verwijderd is."""
    from app.domains.mail.models import EmailLog

    rij = db.query(EmailLog).filter(EmailLog.id == log_id).first()
    if rij is None:
        return False
    db.delete(rij)
    db.commit()
    return True


def send_with_attachments(
    *,
    to_emails: list[str],
    subject: str,
    body_html: str,
    attachments: list[tuple] | None = None,
    reply_to: Optional[str] = None,
    email_type: str = "other",
) -> None:
    """Eén mail naar meerdere ontvangers, met bijlagen (#258, CR-09 §3.13).

    Verschilt bewust van ``_send`` op drie punten, en elk punt is een beslissing:

    - **Iedereen in de To-regel.** De vergaderkring kent elkaar en antwoordt
      elkaar; dit is géén campagne, dus geen Bcc en geen uitschrijflink. De
      nieuwsbrief (CR-05) gaat juist wél per ontvanger — dat is het andere pad.
    - **Bijlagen.** ``(bestandsnaam, content-type, bytes)`` per stuk, in een
      ``multipart/mixed`` om het bestaande ``alternative``-deel heen.
    - **Reply-To.** De afzender blijft het verenigingsadres; antwoorden komen bij
      de beheerder die verstuurt, zodat de gesprekken toekomen waar ze vandaag
      ook toekomen (§3.24).

    Logt één rij per ontvanger in de email_log, zoals elke andere verzending:
    de log beantwoordt "heeft deze persoon dit gekregen?", en dat antwoord mag
    niet afhangen van hoeveel mensen er in dezelfde mail zaten.
    """
    from email import encoders
    from email.mime.base import MIMEBase

    to_emails = [e for e in (to_emails or []) if e]
    if not to_emails:
        return
    joined = ", ".join(to_emails)

    if _mail_mode() == "log_only":
        for address in to_emails:
            _log_email(
                address,
                subject,
                body_html,
                email_type,
                MailStatus.LOGGED,
                "demo-tenant: alleen gelogd, niet verstuurd",
            )
        return

    gmail_user, gmail_password, gmail_from = _gmail_config()
    if not gmail_user or not gmail_password:
        logger.warning(
            "E-mail niet verstuurd (GMAIL_USER/GMAIL_APP_PASSWORD ontbreekt): %s", subject
        )
        for address in to_emails:
            _log_email(
                address,
                subject,
                body_html,
                email_type,
                MailStatus.SKIPPED,
                "GMAIL_USER/GMAIL_APP_PASSWORD niet ingesteld",
            )
        return

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"{_env_prefix()}{subject}"
    from_address = gmail_from or gmail_user
    msg["From"] = f"{_display_name()} <{from_address}>"
    msg["To"] = joined
    if reply_to:
        msg["Reply-To"] = reply_to
    body = MIMEMultipart("alternative")
    body.attach(MIMEText(body_html, "html"))
    msg.attach(body)

    for filename, content_type, data in attachments or []:
        main, _, sub = (content_type or "application/octet-stream").partition("/")
        part = MIMEBase(main or "application", sub or "octet-stream")
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, to_emails, msg.as_string())
    except Exception as exc:
        logger.error("Vergadermail versturen mislukt (%s): %s", joined, exc)
        for address in to_emails:
            _log_email(address, subject, body_html, email_type, MailStatus.FAILED, str(exc))
        raise
    for address in to_emails:
        _log_email(address, subject, body_html, email_type, MailStatus.SENT, None)
