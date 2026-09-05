"""#661 — een openstaande terugbetaling krijgt dezelfde snelkoppeling als een vordering.

"Bevestig betaald" stond achter `r.type != "refund"`, dus een openstaande
terugbetaling moest je via Bewerken openen en het bedrag intypen — terwijl dat
bedrag al bekend is.

De laag eronder kon dit al: `confirm_manual_payment` boekt zonder expliciet bedrag
"het volledige verschuldigde, resp. de volledige refund" (#199) en is
tekengevoelig (#219: charge → [0, amount], refund (negatief) → [amount, 0]). Het
endpoint is niet aangepast.

Het teken is precies wat hier mis kan gaan: een refund die als +bedrag geboekt
wordt, telt op in plaats van af en het saldo klopt stil niet meer.
"""
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.payment.api import PaymentRecord
from tests._invarianten import assert_saldo_klopt
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _make_finance(db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()


def _charge_met_openstaande_refund(db, payable_id: int):
    """€30 ontvangen, €10 nog terug te betalen."""
    from app.domains.payment.api import create_refund

    charge = PaymentRecord(payable_type="membership", payable_id=payable_id,
                           amount=Decimal("30.00"), method="transfer", status="paid")
    charge.amount_paid = Decimal("30.00")
    db.add(charge)
    db.flush()
    refund = create_refund(db, charge.id, Decimal("10.00"), actor="fin@test",
                           settled=False)
    db.commit()
    return charge, refund


def test_bevestigen_zonder_bedrag_boekt_de_volledige_refund_negatief(client, db_session):
    """De kern: status paid én amount_paid gelijk aan het volledige, NEGATIEVE bedrag."""
    _make_finance(db_session)
    charge, refund = _charge_met_openstaande_refund(db_session, payable_id=6610)
    csrf = _login(client)

    r = client.post(f"/admin/betalingen/{refund.id}/bevestigen",
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text[:300]

    db_session.expire_all()
    vers = db_session.get(PaymentRecord, refund.id)
    assert vers.status == "paid"
    assert vers.amount_paid == vers.amount, (
        "zonder bedrag hoort de volledige refund geboekt te worden (#199)")
    assert vers.amount_paid < 0, (
        f"een terugbetaling hoort negatief geboekt te worden, kreeg {vers.amount_paid}")
    assert vers.amount_paid == Decimal("-10.00")

    # €30 in, €10 terug → het saldo blijft €20.
    assert_saldo_klopt(db_session, "membership", 6610, Decimal("20.00"))


def test_de_knop_staat_op_een_openstaande_terugbetaling(client, db_session):
    """Het scherm: label én bevestigingstekst zijn per type anders.

    "Als volledig betaald bevestigen?" op een terugbetaling is misleidend — er
    vertrekt geld, het komt niet binnen.
    """
    _make_finance(db_session)
    _charge, refund = _charge_met_openstaande_refund(db_session, payable_id=6611)
    _login(client)

    html = client.get("/admin/betalingen/lijst").text
    regels = [r for r in html.splitlines()
              if f"/admin/betalingen/{refund.id}/bevestigen" in r]
    assert regels, (
        "de openstaande terugbetaling heeft geen bevestig-knop (#661). Let op: een "
        "refund die uit een charge ontstaat, rendert genest en niet als eigen kaart")
    blok = "\n".join(regels)
    assert "Bevestig terugbetaald" in blok, f"verkeerd label: {blok[:200]}"
    assert "Als volledig terugbetaald bevestigen?" in blok, (
        f"verkeerde bevestigingstekst: {blok[:200]}")


def test_een_gewone_vordering_houdt_haar_eigen_woorden(client, db_session):
    """Geen kudde-effect: de charge blijft "Bevestig betaald"."""
    _make_finance(db_session)
    open_charge = PaymentRecord(payable_type="membership", payable_id=6612,
                                amount=Decimal("25.00"), method="transfer",
                                status="pending")
    db_session.add(open_charge)
    db_session.commit()
    _login(client)

    html = client.get("/admin/betalingen/lijst").text
    regels = [r for r in html.splitlines()
              if f"/admin/betalingen/{open_charge.id}/bevestigen" in r]
    assert regels
    blok = "\n".join(regels)
    assert "Bevestig betaald" in blok and "terugbetaald" not in blok.lower()


def test_een_afgehandelde_terugbetaling_krijgt_de_knop_niet(client, db_session):
    """De status-guard blijft: enkel wat nog openstaat."""
    _make_finance(db_session)
    _charge, refund = _charge_met_openstaande_refund(db_session, payable_id=6613)
    csrf = _login(client)
    client.post(f"/admin/betalingen/{refund.id}/bevestigen",
                headers={"X-CSRF-Token": csrf})

    html = client.get("/admin/betalingen/lijst").text
    regels = [r for r in html.splitlines()
              if f"/admin/betalingen/{refund.id}/bevestigen" in r]
    assert not regels, "een vereffende terugbetaling hoort geen bevestig-knop te tonen"
