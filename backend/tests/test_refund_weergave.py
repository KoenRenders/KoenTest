"""Terugbetaling in de betalingenlijst (#617).

De belangrijkste fout was een correctheidsfout, geen opmaakkwestie: een refund die
nog op `pending` staat rendeerde onvoorwaardelijk als "✓ Terugbetaald", náást de
tekst dat de terugstorting nog bevestigd moet worden. Voor een penningmeester is
net dát de informatie die telt.
"""
from decimal import Decimal

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.payment.api import PaymentRecord


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _charge_met_refund(db, refund_status: str):
    charge = PaymentRecord(
        payable_type="registration", payable_id=4242, type="charge",
        contact_name="An Janssens", description="Testbestelling",
        amount=Decimal("27.50"), amount_paid=Decimal("27.50"),
        status="paid", method="transfer",
    )
    db.add(charge)
    db.flush()
    refund = PaymentRecord(
        payable_type="registration", payable_id=4242, type="refund",
        refund_of_id=charge.id, contact_name="An Janssens",
        description="Automatisch bij bestelverlaging",
        amount=Decimal("-27.50"),
        amount_paid=Decimal("-27.50") if refund_status == "paid" else None,
        status=refund_status, method="transfer",
    )
    db.add(refund)
    db.commit()
    return charge, refund


def test_openstaande_refund_zegt_niet_terugbetaald(client, db_session):
    """De correctheidsfout uit #617-1."""
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
    """#617-2: de dropdowns toonden `pending`/`paid` i.p.v. leesbare labels."""
    _charge_met_refund(db_session, "pending")
    _login(client)

    html = client.get("/admin/betalingen/lijst").text
    assert "In afwachting" in html
    assert ">pending<" not in html and ">cancelled<" not in html


def test_totaalregel_telt_charge_en_refunds_samen(client, db_session):
    """#617-2b: de kop telt enkel de charge, dus met een refund eronder beschrijft
    hij de inschrijving niet meer. € 27,50 betaald + € 27,50 terug = saldo −27,50."""
    _charge_met_refund(db_session, "pending")
    _login(client)

    html = client.get("/admin/betalingen/lijst").text
    assert "Totaal inschrijving" in html
    assert "Terug te storten" in html
    assert "€ 27.50" in html


def test_geen_totaalregel_zonder_refunds(client, db_session):
    """Bij een gewone betaling zou ze enkel de kop herhalen."""
    db_session.add(PaymentRecord(
        payable_type="registration", payable_id=4343, type="charge",
        contact_name="Jan Peeters", description="Zonder refund",
        amount=Decimal("10.00"), amount_paid=Decimal("10.00"),
        status="paid", method="transfer"))
    db_session.commit()
    _login(client)

    html = client.get("/admin/betalingen/lijst").text
    assert "Jan Peeters" in html
    assert "Totaal inschrijving" not in html
