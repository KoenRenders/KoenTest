"""#668 — een gefilterde terugbetaling toont de betaling waarvoor ze loopt.

Zonder die context staat er "10 terug te betalen" zonder te zeggen waarvoor. De
charge komt erbij als **context**, niet als treffer: ingetogen, zonder acties, en
niet meegeteld in het totaal — anders liegt het filter over wat het toont.
"""
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.payment.api import PaymentRecord
from app.domains.payment.service import group_cards
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _records(db):
    """Een betaalde vordering met een nog openstaande terugbetaling eronder."""
    from app.domains.payment.api import create_refund

    charge = PaymentRecord(payable_type="membership", payable_id=6680,
                           amount=Decimal("30.00"), method="transfer", status="paid")
    charge.amount_paid = Decimal("30.00")
    db.add(charge)
    db.flush()
    refund = create_refund(db, charge.id, Decimal("10.00"), actor="fin@test",
                           settled=False)
    db.commit()
    return charge, refund


def test_de_charge_komt_mee_als_context(db_session):
    charge, refund = _records(db_session)

    # Het openstaand-filter laat enkel de refund door; de charge is vereffend.
    groepen = group_cards([refund], [charge, refund])
    assert len(groepen) == 1
    kaarten = groepen[0]["kaarten"]
    assert len(kaarten) == 1, "de refund hoort onder haar charge te hangen"

    kaart_charge, eigen_refunds, is_context = kaarten[0]
    assert kaart_charge.id == charge.id
    assert is_context is True, "de charge is geen treffer maar context"
    assert [r.id for r in eigen_refunds] == [refund.id]


def test_de_contextkaart_telt_niet_mee_in_het_totaal(db_session):
    """Anders zegt het totaal iets anders dan het filter selecteerde."""
    charge, refund = _records(db_session)
    groepen = group_cards([refund], [charge, refund])

    totaal = groepen[0]["totaal"]
    assert totaal["due"] == Decimal("-10.00"), (
        f"enkel de terugbetaling hoort te tellen, kreeg {totaal['due']}")


def test_zonder_alle_records_verandert_er_niets(db_session):
    """De oude aanroepvorm blijft geldig: dan krijg je een wees-kaart, zoals voorheen."""
    _charge, refund = _records(db_session)
    groepen = group_cards([refund])
    kaart_charge, eigen_refunds, is_context = groepen[0]["kaarten"][0]
    assert kaart_charge.id == refund.id and is_context is False
    assert eigen_refunds == []


def test_het_scherm_toont_de_context_ingetogen_en_zonder_acties(client, db_session):
    charge, _refund = _records(db_session)
    gebruiker = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in gebruiker.roles):
        db_session.add(UserRole(user_id=gebruiker.id, role_code="FINANCE"))
        db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get("/admin/betalingen/lijst?openstaand=1").text
    assert "Ter context" in html, "de charge staat er niet als context bij"
    # De contextkaart draagt geen bewerk- of terugbetaalacties.
    blok = html[html.index("Ter context"):]
    blok = blok[:blok.find("Ter context", 1) if blok.find("Ter context", 1) > 0 else len(blok)]
    assert f"/admin/betalingen/{charge.id}/refund" not in blok
