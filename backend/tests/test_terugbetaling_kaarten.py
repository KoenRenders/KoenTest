"""Terugbetalingen: bedragen, afboeken en de kaartopbouw (#617, tweede ronde).

Deze tests komen vóór de herbouw, en met opzet: de bestaande tests toetsen of de tekst
"Totaal inschrijving" op de pagina staat, niet of de **bedragen** kloppen. Een refactor
kan daar ongestraft doorheen breken.

Twee functionele bugs wegen hier zwaarder dan de opmaak:
  - je kon een terugbetaling niet afboeken zonder een minteken te typen;
  - een handmatig aangemaakte terugbetaling stond meteen op "Terugbetaald".
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from app.domains.payment.api import PaymentRecord, get_records_for
from tests._invarianten import assert_saldo_klopt
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_agnostisch

PAYABLE = ("registration", 8811)


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _charge(db, bedrag="10.50", betaald="10.50", method="online", payable_id=PAYABLE[1]):
    rec = PaymentRecord(payable_type="registration", payable_id=payable_id,
                        type="charge", amount=Decimal(bedrag),
                        amount_paid=Decimal(betaald) if betaald else None,
                        method=method, status="paid" if betaald else "pending",
                        paid_at=datetime.now(timezone.utc) if betaald else None)
    db.add(rec)
    db.commit()
    return rec


# ── §2-0: afboeken zonder minteken ──────────────────────────────────────────

def test_afboeken_met_een_positief_bedrag(client, db_session):
    """De zwaarste bug: de penningmeester moest "-40.00" typen om een uitbetaling te
    registreren. Het minteken is een boekhoudkundige interne conventie — dat hoort
    niemand in te typen. De UI spreekt positief, de server rekent negatief."""
    charge = _charge(db_session)
    hdr = _login(client, db_session)
    client.post(f"/admin/betalingen/{charge.id}/refund", headers=hdr, data={"amount": "10.50"})
    refund = [r for r in get_records_for(db_session, *PAYABLE) if r.type == "refund"][0]

    resp = client.post(f"/admin/betalingen/{refund.id}/bewerken", headers=hdr,
                       data={"status": "paid", "amount_paid": "10.50", "note": ""})
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    bijgewerkt = db_session.get(PaymentRecord, refund.id)
    assert bijgewerkt.amount_paid == Decimal("-10.50"), "de server rekent negatief"
    assert bijgewerkt.status == "paid"
    assert_saldo_klopt(db_session, *PAYABLE, "0")


def test_te_veel_afboeken_wordt_geweigerd_in_positieve_termen(client, db_session):
    charge = _charge(db_session)
    hdr = _login(client, db_session)
    client.post(f"/admin/betalingen/{charge.id}/refund", headers=hdr, data={"amount": "10.50"})
    refund = [r for r in get_records_for(db_session, *PAYABLE) if r.type == "refund"][0]

    resp = client.post(f"/admin/betalingen/{refund.id}/bewerken", headers=hdr,
                       data={"status": "pending", "amount_paid": "99.00", "note": ""})
    assert resp.status_code >= 400
    db_session.expire_all()
    assert db_session.get(PaymentRecord, refund.id).amount_paid is None


def test_nul_blijft_toegestaan(client, db_session):
    """De 'corrigeren zodat je hem kunt verwijderen'-route uit de verwijder-guard."""
    charge = _charge(db_session)
    hdr = _login(client, db_session)
    client.post(f"/admin/betalingen/{charge.id}/refund", headers=hdr, data={"amount": "10.50"})
    refund = [r for r in get_records_for(db_session, *PAYABLE) if r.type == "refund"][0]

    resp = client.post(f"/admin/betalingen/{refund.id}/bewerken", headers=hdr,
                       data={"status": "pending", "amount_paid": "0", "note": ""})
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    assert db_session.get(PaymentRecord, refund.id).amount_paid == Decimal("0")


# ── §2-0b: handmatige refund staat niet meteen op betaald ───────────────────

def test_handmatige_refund_start_als_terug_te_betalen(client, db_session):
    """Er is geen weg meer die een refund meteen afboekt: aanmaken en afboeken zijn
    twee stappen, net als bij een betaling."""
    charge = _charge(db_session)
    hdr = _login(client, db_session)

    client.post(f"/admin/betalingen/{charge.id}/refund", headers=hdr,
                data={"amount": "10.50", "note": "handmatig"})

    refund = [r for r in get_records_for(db_session, *PAYABLE) if r.type == "refund"][0]
    assert refund.status == "pending"
    assert refund.amount_paid is None, "er is nog niets gestort"
    assert_saldo_klopt(db_session, *PAYABLE, "0")


# ── §2-0d: het canonieke testgeval, met exacte bedragen ─────────────────────

def test_canoniek_geval_uit_de_v1_14_screenshot(client, db_session):
    """Eén betaalde charge en twee terugbetalingen, waarvan één afgeboekt.

    Rekent de formule uit §2b na met exact deze bedragen:
      Bedrag    10,50 − 10,50 − 10,50 = −10,50
      Ontvangen 10,50 +  0     − 10,50 =   0,00
      Saldo     −10,50 − 0,00           = −10,50

    Let op wat dit bewijst: de **pending** refund telt wél mee in Bedrag maar niet in
    Ontvangen.
    """
    charge = _charge(db_session, bedrag="10.50", betaald="10.50", method="online")
    hdr = _login(client, db_session)

    client.post(f"/admin/betalingen/{charge.id}/refund", headers=hdr, data={"amount": "10.50"})
    client.post(f"/admin/betalingen/{charge.id}/refund", headers=hdr, data={"amount": "10.50"})
    refunds = [r for r in get_records_for(db_session, *PAYABLE) if r.type == "refund"]
    assert len(refunds) == 2

    # De tweede terugbetaling wordt uitbetaald — met een positief bedrag.
    client.post(f"/admin/betalingen/{refunds[1].id}/bewerken", headers=hdr,
                data={"status": "paid", "amount_paid": "10.50", "note": ""})

    db_session.expire_all()
    records = get_records_for(db_session, *PAYABLE)
    bedrag = sum((Decimal(str(r.amount)) for r in records), Decimal("0"))
    ontvangen = sum((Decimal(str(r.amount_paid or 0)) for r in records), Decimal("0"))

    assert bedrag == Decimal("-10.50"), f"Bedrag klopt niet: {bedrag}"
    assert ontvangen == Decimal("0.00"), f"Ontvangen klopt niet: {ontvangen}"
    assert bedrag - ontvangen == Decimal("-10.50"), "Saldo klopt niet"


def test_deels_betaalde_charge_met_refund(client, db_session):
    """Scenario uit §2c dat in de code zit maar nergens getoetst werd."""
    charge = _charge(db_session, bedrag="30.00", betaald="10.00", method="transfer",
                     payable_id=8812)
    hdr = _login(client, db_session)
    client.post(f"/admin/betalingen/{charge.id}/refund", headers=hdr, data={"amount": "10.00"})

    db_session.expire_all()
    records = get_records_for(db_session, "registration", 8812)
    bedrag = sum((Decimal(str(r.amount)) for r in records), Decimal("0"))
    ontvangen = sum((Decimal(str(r.amount_paid or 0)) for r in records), Decimal("0"))
    assert bedrag == Decimal("20.00")      # 30 − 10
    assert ontvangen == Decimal("10.00")   # nog niets teruggestort


# ── §2-0e: één totaalregel per INSCHRIJVING, niet per charge ────────────────

def test_meerdere_charges_geven_een_totaalregel(client, db_session):
    """De totaalregel heette "Totaal inschrijving" maar telde één charge met haar
    refunds. Een inschrijving met meerdere charges — precies wat
    reconcile_registration_charges produceert bij een bestelwijziging — kreeg dus
    meerdere regels die elk iets anders beweerden.

    Het geval uit het issue: € 20 betaald + € 66 betaald + € −5 refund → één regel
    met Bedrag € 81,00 · Ontvangen € 86,00 · Saldo € −5,00.
    """
    payable_id = 8813
    _charge(db_session, bedrag="20.00", betaald="20.00", method="transfer",
            payable_id=payable_id)
    charge2 = _charge(db_session, bedrag="66.00", betaald="66.00", method="transfer",
                      payable_id=payable_id)
    hdr = _login(client, db_session)
    client.post(f"/admin/betalingen/{charge2.id}/refund", headers=hdr, data={"amount": "5.00"})

    html = client.get("/admin/betalingen/lijst").text
    assert html.count("Totaal inschrijving") == 1, "één regel per inschrijving"
    assert "€ 81.00" in html and "€ 86.00" in html and "€ -5.00" in html


def test_refund_met_uitbetaald_bedrag_maar_status_pending(client, db_session):
    """Randgeval uit bestaande data (gevolg van de bug uit §2-0b): de weergave moet
    Ontvangen tonen zodra `amount_paid` gevuld is, ongeacht de status."""
    payable_id = 8814
    charge = _charge(db_session, bedrag="40.00", betaald="40.00", method="transfer",
                     payable_id=payable_id)
    hdr = _login(client, db_session)
    client.post(f"/admin/betalingen/{charge.id}/refund", headers=hdr, data={"amount": "10.00"})
    refund = [r for r in get_records_for(db_session, "registration", payable_id)
              if r.type == "refund"][0]
    refund.amount_paid = Decimal("-5.00")   # pending mét uitbetaald bedrag
    db_session.commit()

    html = client.get("/admin/betalingen/lijst").text
    assert "Terug te betalen" in html, "de badge volgt de status"
    assert "-5.00" in html, "Ontvangen hoort zichtbaar te zijn"
