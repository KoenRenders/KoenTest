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
    from_address = settings.gmail_from or settings.gmail_user
    msg["From"] = f"Raak Millegem <{from_address}>"
    msg["To"] = to_email
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(settings.gmail_user, settings.gmail_app_password)
        server.sendmail(settings.gmail_user, to_email, msg.as_string())


def send_registration_confirmation(to_email: str, name: str, family, data=None, pc_municipality: str = "") -> None:
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

    _send(
        to_email=to_email,
        subject="Welkom bij Raak Millegem!",
        body_html=f"""
        <p>Beste {escape(name)},</p>
        <p>Je registratie bij Raak Millegem is ontvangen. Welkom!</p>
        {details}
        <p>Met vriendelijke groeten,<br>Raak Millegem</p>
        """,
    )


def send_activity_registration_confirmation(
    to_email: str, name: str, activity, registration=None, is_waitlist: bool = False
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
        if registration:
            details = []
            if registration.contact_email:
                details.append(f"<li><strong>E-mail:</strong> {escape(registration.contact_email)}</li>")
            if registration.contact_phone:
                details.append(f"<li><strong>GSM:</strong> {escape(registration.contact_phone)}</li>")
            if registration.team_name:
                details.append(f"<li><strong>Ploeg:</strong> {escape(registration.team_name)}</li>")
            if registration.group_size and registration.group_size > 1:
                details.append(f"<li><strong>Aantal personen:</strong> {registration.group_size}</li>")
            if registration.items:
                items_html = "".join(
                    f"<li>{escape(item.sub_registration.name) if hasattr(item, 'sub_registration') and item.sub_registration else str(item.sub_registration_id)} × {item.quantity}</li>"
                    for item in registration.items
                )
                details.append(f"<li><strong>Producten:</strong><ul>{items_html}</ul></li>")
            if registration.total_amount and registration.total_amount > 0:
                details.append(f"<li><strong>Totaal:</strong> €{registration.total_amount:.2f}</li>")
            if registration.payment_method and registration.payment_method != "FREE":
                method_labels = {"MOLLIE": "Online (Mollie)", "CASH": "Cash", "TRANSFER": "Overschrijving"}
                details.append(f"<li><strong>Betaalmethode:</strong> {method_labels.get(registration.payment_method, registration.payment_method)}</li>")
            if registration.remarks:
                details.append(f"<li><strong>Opmerkingen:</strong> {escape(registration.remarks)}</li>")
            if details:
                message += f"<h4 style='margin-top:12px;margin-bottom:4px'>Jouw gegevens</h4><ul>{''.join(details)}</ul>"
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
