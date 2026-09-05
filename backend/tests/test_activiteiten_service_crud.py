"""#679 — de CRUD van activiteiten woont in de service, niet in de router.

Laatste post van #635. Twintig functies zaten in `activities/router.py`, waar ze
een mengsel vormden van HTTP-afhandeling (404's, `Depends`, de responsvorm) en
domeinregels (audit-snapshots, soft delete van de hele boom, de transactiegrens).
Alleen het tweede hoort in een service.

Bewust GEEN facades die alleen doorgeven: twintig doorgangen zouden de laag-gate
groen zetten zonder dat er iets verandert. Een eerlijke rode regel in de allowlist
is beter dan een groene gate om de verkeerde reden.

**Dit is structuur, geen gedrag.** De bestaande gedragstests blijven ongewijzigd
groen; deze tests leggen alleen vast dat de bewerking nu óók zonder de router
werkt, met dezelfde geschiedenis en dezelfde transactiegrens.
"""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.domains.activities import service
from app.domains.activities.api import Activity, ActivityDate

pytestmark = pytest.mark.ui_agnostisch


def test_aanmaken_werkt_zonder_de_router(db_session):
    datums = [SimpleNamespace(start_date=date.today() + timedelta(days=7),
                              end_date=None, start_time=None, end_time=None)]
    activiteit = service.create_activity(
        db_session, name="Zonder router", location="Zaal", dates=datums,
        actor="test@example.com")

    assert activiteit.id is not None
    assert activiteit.name == "Zonder router"
    assert [d.start_date for d in activiteit.dates] == [datums[0].start_date]


def test_aanmaken_legt_de_geschiedenis_vast(db_session):
    """Een mutatie zonder snapshot is een stille regressie in de geschiedenis."""
    from app.domains.activities.api import ActivityDateHistory, ActivityHistory

    datums = [SimpleNamespace(start_date=date.today(), end_date=None,
                              start_time=None, end_time=None)]
    activiteit = service.create_activity(db_session, name="Met historie",
                                         dates=datums, actor="test@example.com")

    rijen = db_session.query(ActivityHistory).filter(
        ActivityHistory.activity_id == activiteit.id).all()
    assert rijen and rijen[0].action == "activity_created"
    assert rijen[0].actor == "test@example.com"
    assert db_session.query(ActivityDateHistory).filter(
        ActivityDateHistory.activity_id == activiteit.id).count() == 1


def test_bijwerken_geeft_none_bij_een_onbekende_activiteit(db_session):
    """De service kent geen HTTP: de aanroeper beslist wat 'bestaat niet' betekent."""
    assert service.update_activity(db_session, 999999, {"name": "x"}) is None


def test_bijwerken_wijzigt_en_bewaart(db_session):
    activiteit = service.create_activity(db_session, name="Oud", actor="a@b.c")
    vers = service.update_activity(db_session, activiteit.id,
                                   {"name": "Nieuw", "location": "Elders"},
                                   actor="a@b.c")
    assert vers.name == "Nieuw" and vers.location == "Elders"


def test_verwijderen_neemt_de_boom_mee_maar_niet_de_betalingen(db_session):
    """Soft delete van datums, onderdelen, producten en inschrijvingen (#166).
    Betalingen blijven: financieel feit — dezelfde regel die #667 vastlegde."""
    from decimal import Decimal

    from app.domains.payment.api import PaymentRecord, get_records_for
    from tests.conftest import seed_activity_with_product

    activiteit, comp, product = seed_activity_with_product(db_session)
    db_session.add(PaymentRecord(payable_type="registration", payable_id=6790,
                                 amount=Decimal("10.00"), method="transfer",
                                 status="pending"))
    db_session.commit()

    assert service.delete_activity(db_session, activiteit.id, actor="a@b.c") is True

    db_session.expire_all()
    assert db_session.query(Activity).filter(Activity.id == activiteit.id).first() is None
    assert db_session.query(ActivityDate).filter(
        ActivityDate.activity_id == activiteit.id).count() == 0
    # De betaling staat er nog.
    assert get_records_for(db_session, "registration", 6790)


def test_verwijderen_geeft_false_bij_een_onbekende_activiteit(db_session):
    assert service.delete_activity(db_session, 999999) is False


def test_de_router_rekent_niet_meer_zelf(db_session):
    """De scheiding zelf: wat overblijft in de route is HTTP, geen domeinlogica."""
    bron = open("app/domains/activities/router.py", encoding="utf-8").read()
    for naam in ("def create_activity(", "def update_activity(", "def delete_activity("):
        start = bron.index(naam)
        einde = bron.index("\n@router", start)
        body = bron[start:einde]
        assert "service." in body, f"{naam} roept de service niet aan"
        assert "snapshot_" not in body, (
            f"{naam} schrijft nog zelf geschiedenis — dat hoort in de service")
        assert "soft_delete(" not in body, (
            f"{naam} verwijdert nog zelf — dat hoort in de service")
