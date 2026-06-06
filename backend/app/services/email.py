import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Optional

from app.config import settings


def _send(to_email: str, subject: str, body_html: str) -> None:
    if not settings.gmail_user or not settings.gmail_app_password:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Raak Millegem <{settings.gmail_user}>"
    msg["To"] = to_email
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(settings.gmail_user, settings.gmail_app_password)
        server.sendmail(settings.gmail_user, to_email, msg.as_string())


def send_registration_confirmation(to_email: str, name: str, family) -> None:
    _send(
        to_email=to_email,
        subject="Welkom bij Raak Millegem!",
        body_html=f"""
        <p>Beste {escape(name)},</p>
        <p>Je registratie bij Raak Millegem is ontvangen. Welkom!</p>
        <p>Met vriendelijke groeten,<br>Raak Millegem</p>
        """,
    )


def send_activity_registration_confirmation(
    to_email: str, name: str, activity, is_waitlist: bool = False
) -> None:
    activity_name = escape(activity.name)
    if is_waitlist:
        subject = f"Wachtlijst: {activity_name}"
        message = f"""
        <p>Je staat op de wachtlijst voor <strong>{activity_name}</strong>.</p>
        <p>Je ontvangt automatisch een bericht als er een plaatsje vrijkomt.</p>
        """
    else:
        subject = f"Inschrijving bevestigd: {activity_name}"
        date_str = activity.date.strftime("%d/%m/%Y")
        time_str = activity.time.strftime("%H:%M") if activity.time else ""
        location = escape(activity.location) if activity.location else ""
        message = f"""
        <p>Je inschrijving voor <strong>{activity_name}</strong> is bevestigd.</p>
        <ul>
          <li><strong>Datum:</strong> {date_str}</li>
          {'<li><strong>Tijdstip:</strong> ' + time_str + '</li>' if time_str else ''}
          {'<li><strong>Locatie:</strong> ' + location + '</li>' if location else ''}
        </ul>
        """
    _send(
        to_email=to_email,
        subject=subject,
        body_html=f"<p>Beste {escape(name)},</p>{message}<p>Met vriendelijke groeten,<br>Raak Millegem</p>",
    )


def send_waitlist_notification(to_email: str, name: str, activity_name: str) -> None:
    _send(
        to_email=to_email,
        subject=f"Plaatsje vrijgekomen: {escape(activity_name)}",
        body_html=f"""
        <p>Beste {escape(name)},</p>
        <p>Er is een plaatsje vrijgekomen voor <strong>{escape(activity_name)}</strong>. Je bent automatisch ingeschreven.</p>
        <p>Met vriendelijke groeten,<br>Raak Millegem</p>
        """,
    )


def send_order_confirmation(to_email: str, name: str, order) -> None:
    items_html = "".join(
        f"<tr><td>{item.product.name}</td><td>{item.quantity}</td><td>€{item.unit_price:.2f}</td></tr>"
        for item in order.items
    )
    _send(
        to_email=to_email,
        subject=f"Bestelling bevestigd – {order.confirmation_number}",
        body_html=f"""
        <p>Beste {name},</p>
        <p>Je bestelling <strong>{order.confirmation_number}</strong> is ontvangen.</p>
        <table border="1" cellpadding="5">
          <tr><th>Product</th><th>Aantal</th><th>Prijs</th></tr>
          {items_html}
          <tr><td colspan="2"><strong>Totaal</strong></td><td><strong>€{order.total_amount:.2f}</strong></td></tr>
        </table>
        <p>Betaalstatus: {order.payment_status}</p>
        <p>Met vriendelijke groeten,<br>Raak Millegem</p>
        """,
    )


def send_idea_acknowledgement(to_email: str, name: str, message: str) -> None:
    _send(
        to_email=to_email,
        subject="Idee ontvangen – Raak Millegem",
        body_html=f"""
        <p>Beste {escape(name)},</p>
        <p>Bedankt voor je idee! We bekijken het zo snel mogelijk.</p>
        <blockquote style="border-left:4px solid #ccc;padding-left:12px;color:#555;">{escape(message)}</blockquote>
        <p>Met vriendelijke groeten,<br>Raak Millegem</p>
        """,
    )
