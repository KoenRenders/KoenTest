"""Terugbetaling in de betalingenlijst (#617).

De belangrijkste fout was een correctheidsfout, geen opmaakkwestie: een refund die
nog op `pending` staat rendeerde onvoorwaardelijk als "✓ Terugbetaald", náást de
tekst dat de terugstorting nog bevestigd moest worden. Voor een penningmeester is
net dát de informatie die telt.
"""

import pytest
pytestmark = pytest.mark.ui_serverrendered
from decimal import Decimal

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.payment.api import PaymentRecord


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _make_finance(db):
    """De editors en rij-acties zijn FINANCE-only (rollen-matrix #544)."""
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()


def _charge_met_refund(db, refund_status: str, payable_id: int = 4242):
    charge = PaymentRecord(payable_type="registration", payable_id=payable_id,
                           amount=Decimal("27.50"), amount_paid=Decimal("27.50"),
                           method="transfer", status="paid", type="charge")
    db.add(charge)
    db.flush()
    refund = PaymentRecord(
        payable_type="registration", payable_id=payable_id,
        amount=Decimal("-27.50"),
        amount_paid=Decimal("-27.50") if refund_status == "paid" else None,
        method="transfer", status=refund_status, type="refund",
        refund_of_id=charge.id, note="Automatisch bij bestelverlaging")
    db.add(refund)
    db.commit()
    return charge, refund


def test_openstaande_refund_zegt_niet_terugbetaald(client, db_session):
    """De correctheidsfout uit #617-1: pending mag nooit als betaald renderen."""
    _charge_met_refund(db_session, "pending")
    _login(client)

    html = client.get("/admin/betalingen/lijst").text
    assert "Terug te betalen" in html
    assert "✓ Terugbetaald" not in html


def test_uitbetaalde_refund_zegt_wel_terugbetaald(client, db_session):
    _charge_met_refund(db_session, "paid")
    _login(client)

    assert "Terugbetaald" in client.get("/admin/betalingen/lijst").text


def test_geen_rauwe_statuscodes_in_de_editors(client, db_session):
    """#617-2: de statusdropdowns toonden `pending`/`cancelled` i.p.v. labels."""
    _make_finance(db_session)
    _charge_met_refund(db_session, "pending")
    _login(client)

    html = client.get("/admin/betalingen/lijst").text
    assert "In afwachting" in html
    assert ">pending<" not in html and ">cancelled<" not in html


def test_totaalregel_telt_charge_en_refunds_samen(client, db_session):
    """#617-2b: de kop telt enkel de charge, dus met een refund eronder beschrijft
    hij de inschrijving niet meer. € 27,50 ontvangen + € 27,50 terug = saldo −27,50."""
    _charge_met_refund(db_session, "pending")
    _login(client)

    html = client.get("/admin/betalingen/lijst").text
    assert "Totaal inschrijving" in html
    # Sinds #617-2c draagt de totaalregel dezelfde labels als de kaarten en doet het
    # teken het werk: een negatief saldo betekent dat wij moeten terugstorten.
    assert "Saldo: € -27.50" in html


def test_geen_totaalregel_zonder_refunds(client, db_session):
    """Bij een gewone betaling zou de regel enkel de kop herhalen."""
    db_session.add(PaymentRecord(
        payable_type="registration", payable_id=4343, amount=Decimal("10.00"),
        amount_paid=Decimal("10.00"), method="transfer", status="paid", type="charge",
        structured_communication="+++111/1111/11111+++"))
    db_session.commit()
    _login(client)

    html = client.get("/admin/betalingen/lijst").text
    assert "+++111/1111/11111+++" in html
    assert "Totaal inschrijving" not in html
