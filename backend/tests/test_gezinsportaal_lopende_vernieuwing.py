"""Gezinsportaal toont een lopende vernieuwing i.p.v. het formulier (#618).

Na een vernieuwing via overschrijving verscheen bij een volgend bezoek opnieuw het
vernieuwformulier — en de knop liep gegarandeerd op de guard ("Je vernieuwing loopt
nog"). De server deed het juiste; het scherm nodigde uit tot een handeling die niet
kon slagen.

De invariant die telt: **guard en scherm zijn het altijd eens**. Beide stellen nu
dezelfde vraag via `open_renewal_payment()`.
"""

import pytest
pytestmark = pytest.mark.ui_serverrendered
from datetime import date
from decimal import Decimal

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.membership.api import Membership, open_renewal_payment
from app.domains.payment.api import GatewayPayment, PaymentRecord
from tests.conftest import create_test_family

FORMULIER = "Lidmaatschap vernieuwen"


def _login_as(client, email):
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _openstaande_vernieuwing(db, member, method="transfer", gateway_payment_id=None):
    """Een niet-betaalde vernieuwing, zoals de renew-flow ze achterlaat."""
    jaar = date.today().year + 1
    ms = Membership(member_id=member.id, year=jaar, is_active=False,
                    valid_from=date(jaar, 1, 1), valid_to=date(jaar, 12, 31))
    db.add(ms)
    db.flush()
    rec = PaymentRecord(payable_type="membership", payable_id=ms.id,
                        amount=Decimal("35.00"), method=method, status="pending",
                        structured_communication="+++123/4567/89012+++",
                        gateway_payment_id=gateway_payment_id)
    db.add(rec)
    db.commit()
    return ms, rec


def test_overschrijving_toont_instructies_bij_een_verse_get(client, db_session):
    """De kern van #618: navigeren weg en terug mag het formulier niet terugbrengen."""
    member, _person = create_test_family(db_session, email="vern@example.com")
    _, rec = _openstaande_vernieuwing(db_session, member)
    _login_as(client, "vern@example.com")

    html = client.get("/leden/gezin").text
    assert "+++123/4567/89012+++" in html
    assert "35.00" in html
    assert FORMULIER not in html


def test_afgebroken_online_betaling_toont_hervatknop(client, db_session):
    """#618-3: even doodlopend als de overschrijving, dus ook afgevangen."""
    member, _person = create_test_family(db_session, email="online@example.com")
    gw = GatewayPayment(amount=Decimal("35.00"), currency="EUR", status="open",
                        provider="mollie", checkout_url="https://betaal.example/hervat")
    db_session.add(gw)
    db_session.flush()
    _openstaande_vernieuwing(db_session, member, method="online",
                             gateway_payment_id=gw.id)
    _login_as(client, "online@example.com")

    html = client.get("/leden/gezin").text
    assert "Betaling hervatten" in html
    assert "https://betaal.example/hervat" in html
    assert FORMULIER not in html


def test_online_zonder_checkout_url_toont_uitleg(client, db_session):
    member, _person = create_test_family(db_session, email="geenurl@example.com")
    _openstaande_vernieuwing(db_session, member, method="online")
    _login_as(client, "geenurl@example.com")

    html = client.get("/leden/gezin").text
    assert "Betaling hervatten" not in html
    assert FORMULIER not in html
    assert "nog niet afgerond" in html


def test_betaalde_vernieuwing_blokkeert_het_scherm_niet(client, db_session):
    """Zodra de betaling `paid` is, hoort het scherm weer normaal te zijn — precies
    zoals de guard dan weer doorlaat."""
    member, _person = create_test_family(db_session, email="betaald@example.com")
    _, rec = _openstaande_vernieuwing(db_session, member)
    rec.status = "paid"
    db_session.commit()
    _login_as(client, "betaald@example.com")

    html = client.get("/leden/gezin").text
    assert "+++123/4567/89012+++" not in html


def test_guard_en_scherm_stellen_dezelfde_vraag(client, db_session):
    """Eén bron (#618-1): de functie die de guard gebruikt, voedt ook het scherm."""
    member, _person = create_test_family(db_session, email="bron@example.com")
    assert open_renewal_payment(db_session, member) is None

    _, rec = _openstaande_vernieuwing(db_session, member)
    assert open_renewal_payment(db_session, member).id == rec.id

    rec.status = "cancelled"
    db_session.commit()
    assert open_renewal_payment(db_session, member) is None
