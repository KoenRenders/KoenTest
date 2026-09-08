"""#720 — een gedeeltelijke betaling maakt een vordering niet "Vereffend".

€ 10,00 invullen op een vordering van € 35,00 en bevestigen leverde de badge
"Vereffend" op, terwijl dezelfde kaart € 25,00 saldo toonde — en dat saldo telde in
de totaalmatrix gewoon rood mee. Het scherm sprak zichzelf tegen op één regel.

`confirm_manual_payment` zette `status = "paid"` onvoorwaardelijk; de enige controle
op het bedrag was een bereikcontrole. `derived_status` kon dat daarna niet meer
rechtzetten, want de tak die "Deels betaald" oplevert vraagt `status == "pending"`.

**Wat zwaarder weegt dan de badge, en waarom de laatste twee tests hier de kern
zijn.** Dezelfde functie activeerde het lidmaatschap, óók onvoorwaardelijk. Wie
€ 10,00 van € 35,00 overmaakte kreeg dus een geldig lidmaatschap terwijl de
resterende € 25,00 open bleef staan zonder iets tegen te houden. Dat is geen
weergavefout meer.

Die twee horen samen: een test die enkel toetst dat een gedeeltelijke betaling niet
activeert, staat óók groen wanneer de activering helemaal stuk is. De tegenhanger —
volledig betalen activeert wél — is wat haar betekenis geeft.

Getoetst wordt het RECORD, niet de statuscode: bevestigen slaagde vandaag ook, het
boekte alleen het verkeerde oordeel.

Kapotgemaakt om te controleren dat elke test rood kan worden (lokaal, met
scripts/test-local.sh):
  * `record.status = "paid" if volledig else "pending"` terug op `= "paid"` → de
    twee gedeeltelijk-tests vallen om, de volledig-tests blijven groen;
  * `and volledig` weer uit de membership-tak gehaald → alleen de vierde test valt
    om, en dat is precies de bedoeling van dat paar;
  * `abs()` uit de vergelijking gehaald → alleen de gedeeltelijke refund valt om
    (€ -5,00 >= € -20,00 is waar, dus "volledig"); de charge-tests merken er niets
    van, want daar is het teken positief. Dat die ene test het enige verschil maakt,
    is precies waarom hij er staat.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.domains.membership.api import Membership
from app.domains.payment.api import PaymentRecord
from app.domains.payment.service import (confirm_manual_payment, create_refund,
                                         derived_status)
from tests.conftest import create_test_member

pytestmark = pytest.mark.ui_agnostisch


def _lidmaatschap(db) -> Membership:
    """Een nog niet actief lidmaatschap met een openstaande vordering van € 35,00."""
    member = create_test_member(db)
    jaar = date.today().year
    ms = Membership(member_id=member.id, year=jaar, is_active=False)
    db.add(ms)
    db.flush()
    return ms


def _vordering(db, ms: Membership, bedrag="35.00") -> PaymentRecord:
    record = PaymentRecord(payable_type="membership", payable_id=ms.id, type="charge",
                           amount=Decimal(bedrag), method="transfer", status="pending")
    db.add(record)
    db.flush()
    return record


# ── De badge volgt de cijfers ────────────────────────────────────────────────

def test_gedeeltelijk_bevestigen_laat_de_vordering_openstaan(db_session):
    """Het gemelde geval: € 10,00 op € 35,00."""
    ms = _lidmaatschap(db_session)
    record = _vordering(db_session, ms)

    confirm_manual_payment(db_session, record.id, amount_paid=Decimal("10.00"),
                           actor="test")

    assert record.status == "pending", "een gedeeltelijke betaling vereffent niets"
    assert derived_status(record) == "partial"
    assert record.amount_paid == Decimal("10.00")


def test_volledig_bevestigen_vereffent_wel(db_session):
    """De tegenhanger. Zonder haar zou "altijd pending" ook groen staan."""
    ms = _lidmaatschap(db_session)
    record = _vordering(db_session, ms)

    confirm_manual_payment(db_session, record.id, amount_paid=Decimal("35.00"),
                           actor="test")

    assert record.status == "paid"
    assert derived_status(record) == "paid"


def test_bevestigen_zonder_bedrag_boekt_het_volle_bedrag(db_session):
    """#199 mag hier niet sneuvelen: één klik "betaald" blijft het hele bedrag."""
    ms = _lidmaatschap(db_session)
    record = _vordering(db_session, ms)

    confirm_manual_payment(db_session, record.id, actor="test")

    assert record.amount_paid == Decimal("35.00")
    assert record.status == "paid"


# ── Het gevolg dat geld en rechten raakt ─────────────────────────────────────

def test_een_gedeeltelijke_betaling_activeert_het_lidmaatschap_niet(db_session):
    """De belangrijkste test van dit issue.

    De activering hing aan de aanroep in plaats van aan het bedrag, dus € 10,00 van
    € 35,00 leverde een geldig lidmaatschap op met € 25,00 nog open.
    """
    ms = _lidmaatschap(db_session)
    record = _vordering(db_session, ms)

    confirm_manual_payment(db_session, record.id, amount_paid=Decimal("10.00"),
                           actor="test")

    db_session.expire_all()
    assert db_session.get(Membership, ms.id).is_active is False, (
        "een deelbetaling mag geen geldig lidmaatschap opleveren")


def test_een_volledige_betaling_activeert_het_lidmaatschap_wel(db_session):
    """Het paar bij de vorige test — die bewijst zonder deze niets.

    Sloopt iemand de activering helemaal, dan blijft de test hierboven groen. Deze
    is wat "niet activeren bij een deelbetaling" onderscheidt van "nooit activeren".
    """
    ms = _lidmaatschap(db_session)
    record = _vordering(db_session, ms)

    confirm_manual_payment(db_session, record.id, amount_paid=Decimal("35.00"),
                           actor="test")

    db_session.expire_all()
    assert db_session.get(Membership, ms.id).is_active is True


# ── Het teken: een terugbetaling draagt een negatief bedrag ──────────────────

def test_een_gedeeltelijk_uitbetaalde_terugbetaling_blijft_openstaan(db_session):
    """Zonder tekengevoeligheid keert het oordeel hier precies om (#219).

    Bij een refund is "volledig" de MEEST NEGATIEVE waarde. Een vergelijking als
    `betaald >= verschuldigd` zou € -5,00 op € -20,00 als volledig zien.
    """
    ms = _lidmaatschap(db_session)
    charge = _vordering(db_session, ms, bedrag="30.00")
    confirm_manual_payment(db_session, charge.id, amount_paid=Decimal("30.00"),
                           actor="test")
    refund = create_refund(db_session, charge.id, Decimal("20.00"),
                           note="test", actor="test", settled=False)

    confirm_manual_payment(db_session, refund.id, amount_paid=Decimal("-5.00"),
                           actor="test")

    assert refund.status == "pending", "een deels uitbetaalde terugbetaling is niet af"
    # Bij een refund wint "moet nog uitbetaald worden" van "deels": `derived_status`
    # toetst `type == "refund"` vóór de partial-tak. Dat is bestaand gedrag en het
    # klopt — er staat nog geld open. Waar het hier om gaat is dat ze NIET op "paid"
    # komt te staan.
    assert derived_status(refund) == "refund_due"


def test_een_volledig_uitbetaalde_terugbetaling_is_af(db_session):
    """De tegenhanger op dezelfde as."""
    ms = _lidmaatschap(db_session)
    charge = _vordering(db_session, ms, bedrag="30.00")
    confirm_manual_payment(db_session, charge.id, amount_paid=Decimal("30.00"),
                           actor="test")
    refund = create_refund(db_session, charge.id, Decimal("20.00"),
                           note="test", actor="test", settled=False)

    confirm_manual_payment(db_session, refund.id, amount_paid=Decimal("-20.00"),
                           actor="test")

    assert refund.status == "paid"
