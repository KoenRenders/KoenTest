"""The way back of a record opened from a booking (CR-11 block 5, #1557).

"‹ Betaling van <naam>": the payment domain names the origin (`register_origin`),
the activity's head only shows it. The link leads back to the payments list as it
was left — its filter and page — with the booking named in `?boeking=`.
"""

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.payment.models import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _booked_activity(client, db):
    activity, component, product = seed_activity_with_product(db, price="10.00", is_free=False)
    client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            "contact_name": "An Voorbeeld",
            "contact_email": "an@example.com",
            "phone": "047",
            f"product_{product.id}": "1",
            "payment_method": "transfer",
        },
    )
    record = db.query(PaymentRecord).one()
    return activity, record


def _way_back(html: str) -> str:
    start = html.index("<a data-way-back")
    return html[start : html.index("</a>", start)]


def test_from_a_booking_the_way_back_names_the_booking_and_keeps_the_list(client, db_session):
    activity, record = _booked_activity(client, db_session)
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    origin = f"/admin/betalingen?zicht=openstaand&pagina=2&boeking={record.id}"
    from urllib.parse import quote

    html = client.get(f"/admin/activiteiten/{activity.id}?terug={quote(origin, safe='')}").text
    back = _way_back(html)
    assert "Betaling van An Voorbeeld" in back
    assert f'href="/admin/betalingen?zicht=openstaand&amp;pagina=2&amp;boeking={record.id}"' in back
    # …and on the next tab as well: the head does not move.
    tab = re.search(r'href="([^"]+/inschrijvingen\?terug=[^"]+)"', html).group(1)
    assert "Betaling van An Voorbeeld" in _way_back(client.get(tab.replace("&amp;", "&")).text)


def test_the_payments_list_without_a_booking_is_named_by_its_menu(client, db_session):
    activity, _record = _booked_activity(client, db_session)
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    html = client.get(
        f"/admin/activiteiten/{activity.id}?terug=%2Fadmin%2Fbetalingen%3Fzicht%3Dopenstaand"
    ).text
    back = _way_back(html)
    assert ">Betalingen<" in back and "Betaling van" not in back


def test_a_booking_that_does_not_exist_is_not_named(client, db_session):
    """A made-up id (or another tenant's: the enrichment only sees this tenant's
    records) leaves the menu name; nothing is echoed from the URL."""
    activity, _record = _booked_activity(client, db_session)
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    html = client.get(
        f"/admin/activiteiten/{activity.id}?terug=%2Fadmin%2Fbetalingen%3Fboeking%3Dniet-bestaand"
    ).text
    back = _way_back(html)
    assert ">Betalingen<" in back and "niet-bestaand" not in back.split(">")[-1]
