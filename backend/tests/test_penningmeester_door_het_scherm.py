"""De penningmeester-handelingen, dóór het scherm heen (#622, laag 2b).

De servicelaag is al gedekt (test_payment_edit_editor, test_payment_admin_actions,
test_payment_refunds). Het gat zit tussen die service en wat de penningmeester **ziet**:
daar zaten #613, #616 en #617. Deze tests POSTen naar de admin-route en asserteren op
de teruggegeven HTML.

P8 is de kern en loopt door élke test: **wat op het scherm staat en wat in de databank
staat mogen niet uit elkaar lopen.** Bij #617 klopte de databank en loog het scherm —
geen enkele bedragtest had dat gevangen.
"""
from decimal import Decimal

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from app.domains.payment.api import PaymentRecord, get_records_for
from tests._invarianten import (assert_geen_pending_als_betaald, assert_geen_wezen,
                                assert_saldo_klopt)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

PAYABLE = ("registration", 7777)


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _charge(db, bedrag="30.00", betaald=None, status="pending"):
    rec = PaymentRecord(payable_type=PAYABLE[0], payable_id=PAYABLE[1], type="charge",
                        amount=Decimal(bedrag),
                        amount_paid=Decimal(betaald) if betaald else None,
                        method="transfer", status=status)
    db.add(rec)
    db.commit()
    return rec


def _post(client, hdr, pad, **data):
    resp = client.post(pad, data=data, headers=hdr)
    assert resp.status_code == 200, resp.text
    return resp.text


def test_P1_bevestig_betaald_toont_de_volle_som(client, db_session):
    charge = _charge(db_session)
    hdr = _login(client, db_session)

    html = _post(client, hdr, f"/admin/betalingen/{charge.id}/bevestigen")

    assert "Openstaand" not in html
    assert "30.00" in html
    assert_saldo_klopt(db_session, *PAYABLE, "30.00")
    assert_geen_pending_als_betaald(html)


def test_P2_status_paid_met_leeg_bedrag_boekt_volledig(client, db_session):
    charge = _charge(db_session)
    hdr = _login(client, db_session)

    html = _post(client, hdr, f"/admin/betalingen/{charge.id}/bewerken",
                 status="paid", amount_paid="", note="")

    db_session.expire_all()
    assert db_session.get(PaymentRecord, charge.id).amount_paid == Decimal("30.00")
    assert "Openstaand" not in html
    assert_saldo_klopt(db_session, *PAYABLE, "30.00")


def test_P3_deelbedrag_laat_het_restant_openstaan(client, db_session):
    charge = _charge(db_session)
    hdr = _login(client, db_session)

    html = _post(client, hdr, f"/admin/betalingen/{charge.id}/bewerken",
                 status="pending", amount_paid="10.00", note="")

    assert "Openstaand" in html, "de rest hoort zichtbaar te blijven"
    assert "20.00" in html
    assert_saldo_klopt(db_session, *PAYABLE, "30.00")


def test_P4_refund_verschijnt_als_nog_terug_te_betalen(client, db_session):
    """#617: een verse refund staat op pending en mag niet als betaald renderen."""
    charge = _charge(db_session, betaald="30.00", status="paid")
    hdr = _login(client, db_session)

    html = _post(client, hdr, f"/admin/betalingen/{charge.id}/refund", amount="30.00")

    assert "Terug te betalen" in html
    assert_geen_pending_als_betaald(html)
    assert_saldo_klopt(db_session, *PAYABLE, "0")


def test_P5_uitbetaling_registreren_brengt_de_groep_op_nul(client, db_session):
    charge = _charge(db_session, betaald="30.00", status="paid")
    hdr = _login(client, db_session)
    _post(client, hdr, f"/admin/betalingen/{charge.id}/refund", amount="30.00")
    refund = [r for r in get_records_for(db_session, *PAYABLE) if r.type == "refund"][0]

    html = _post(client, hdr, f"/admin/betalingen/{refund.id}/bewerken",
                 status="paid", amount_paid="-30.00", note="")

    assert "Terugbetaald" in html
    netto = sum((Decimal(str(r.amount_paid or 0))
                 for r in get_records_for(db_session, *PAYABLE)), Decimal("0"))
    assert netto == Decimal("0"), "ontvangen − teruggestort = 0"
    assert_saldo_klopt(db_session, *PAYABLE, "0")


def test_P6_deeluitbetaling_laat_het_restant_zien(client, db_session):
    charge = _charge(db_session, betaald="30.00", status="paid")
    hdr = _login(client, db_session)
    _post(client, hdr, f"/admin/betalingen/{charge.id}/refund", amount="30.00")
    refund = [r for r in get_records_for(db_session, *PAYABLE) if r.type == "refund"][0]

    _post(client, hdr, f"/admin/betalingen/{refund.id}/bewerken",
          status="pending", amount_paid="-10.00", note="")

    netto = sum((Decimal(str(r.amount_paid or 0))
                 for r in get_records_for(db_session, *PAYABLE)), Decimal("0"))
    assert netto == Decimal("20.00"), "er moet nog € 20 terug"
    assert_saldo_klopt(db_session, *PAYABLE, "0")


def test_P7_twee_terugbetalingen_tellen_allebei_mee(client, db_session):
    charge = _charge(db_session, betaald="30.00", status="paid")
    hdr = _login(client, db_session)
    _post(client, hdr, f"/admin/betalingen/{charge.id}/refund", amount="10.00")
    html = _post(client, hdr, f"/admin/betalingen/{charge.id}/refund", amount="5.00")

    refunds = [r for r in get_records_for(db_session, *PAYABLE) if r.type == "refund"]
    assert len(refunds) == 2
    assert "Totaal inschrijving" in html, "de groepstotaalregel hoort er te staan (#617)"
    assert_saldo_klopt(db_session, *PAYABLE, "15.00")


def test_P8_er_blijven_geen_weesrecords_achter(client, db_session):
    charge = _charge(db_session, betaald="30.00", status="paid")
    hdr = _login(client, db_session)
    _post(client, hdr, f"/admin/betalingen/{charge.id}/refund", amount="30.00")

    assert_geen_wezen(db_session)
