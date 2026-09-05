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


# ── Batch 2: datums ───────────────────────────────────────────────────────────

def test_een_datum_toevoegen_zonder_de_router(db_session):
    from types import SimpleNamespace

    activiteit = service.create_activity(db_session, name="Met datum", actor="a@b.c")
    ad = service.add_activity_date(
        db_session, activiteit.id,
        SimpleNamespace(start_date=date.today(), end_date=None,
                        start_time=None, end_time=None),
        actor="a@b.c")
    assert ad is not None and ad.activity_id == activiteit.id


def test_een_datum_van_een_andere_activiteit_is_niet_te_bewerken(db_session):
    """De sleutel is (activiteit, datum), en dat hoort in de service.

    Zou alleen de route dat controleren, dan kan elke andere ingang een datum van
    activiteit A via activiteit B bewerken.
    """
    from types import SimpleNamespace

    a = service.create_activity(db_session, name="A", actor="a@b.c")
    b = service.create_activity(db_session, name="B", actor="a@b.c")
    datum = service.add_activity_date(
        db_session, a.id,
        SimpleNamespace(start_date=date.today(), end_date=None,
                        start_time=None, end_time=None), actor="a@b.c")

    assert service.update_activity_date(db_session, b.id, datum.id,
                                        {"start_date": date.today()}) is None
    assert service.delete_activity_date(db_session, b.id, datum.id) is False
    # En via de eigen activiteit werkt het wél.
    assert service.delete_activity_date(db_session, a.id, datum.id) is True


def test_een_datum_bijwerken_bewaart_de_geschiedenis(db_session):
    from types import SimpleNamespace

    from app.domains.activities.api import ActivityDateHistory

    activiteit = service.create_activity(db_session, name="Historie", actor="a@b.c")
    datum = service.add_activity_date(
        db_session, activiteit.id,
        SimpleNamespace(start_date=date.today(), end_date=None,
                        start_time=None, end_time=None), actor="a@b.c")
    service.update_activity_date(db_session, activiteit.id, datum.id,
                                 {"start_date": date.today() + timedelta(days=1)},
                                 actor="a@b.c")

    acties = [r.action for r in db_session.query(ActivityDateHistory).filter(
        ActivityDateHistory.activity_id == activiteit.id).all()]
    assert "date_created" in acties and "date_updated" in acties


# ── Batch 3: onderdelen en producten ──────────────────────────────────────────

def _onderdeel_gegevens(naam="Onderdeel"):
    return SimpleNamespace(name=naam, team_name_required=False, sort_order=0,
                           external_register_url=None, external_registrations_url=None,
                           info_url=None, max_participants=None)


def _product_gegevens(naam="Product", is_free=False, pay_on_site=False):
    from decimal import Decimal

    return SimpleNamespace(name=naam, price=Decimal("10.00"), member_price=None,
                           is_free=is_free, pay_on_site=pay_on_site,
                           max_participants=None, sort_order=0)


def test_een_onderdeel_toevoegen_en_verwijderen(db_session):
    activiteit = service.create_activity(db_session, name="Met onderdeel", actor="a@b.c")
    comp = service.add_component(db_session, activiteit.id, _onderdeel_gegevens(),
                                 actor="a@b.c")
    assert comp is not None and comp.activity_id == activiteit.id
    assert service.delete_component(db_session, activiteit.id, comp.id,
                                    actor="a@b.c") is True


def test_een_onderdeel_verwijderen_neemt_zijn_producten_mee(db_session):
    from app.domains.activities.api import ActivityProduct

    activiteit = service.create_activity(db_session, name="Boom", actor="a@b.c")
    comp = service.add_component(db_session, activiteit.id, _onderdeel_gegevens(),
                                 actor="a@b.c")
    prod = service.add_product(db_session, activiteit.id, comp.id,
                               _product_gegevens(), actor="a@b.c")
    assert prod is not None

    service.delete_component(db_session, activiteit.id, comp.id, actor="a@b.c")
    db_session.expire_all()
    assert db_session.query(ActivityProduct).filter(
        ActivityProduct.id == prod.id).first() is None


def test_gratis_en_ter_plaatse_sluiten_elkaar_uit(db_session):
    """Een DOMEINregel, dus ze geldt ook zonder de route.

    Stond ze in de router, dan kon elke andere ingang het paar gewoon opslaan.
    """
    activiteit = service.create_activity(db_session, name="Afrekening", actor="a@b.c")
    comp = service.add_component(db_session, activiteit.id, _onderdeel_gegevens(),
                                 actor="a@b.c")

    with pytest.raises(service.ActiviteitFout):
        service.add_product(db_session, activiteit.id, comp.id,
                            _product_gegevens(is_free=True, pay_on_site=True),
                            actor="a@b.c")


def test_de_regel_geldt_ook_als_je_er_via_een_wijziging_in_belandt(db_session):
    """Eén veld wijzigen kan de verboden combinatie alsnog opleveren."""
    activiteit = service.create_activity(db_session, name="Afrekening 2", actor="a@b.c")
    comp = service.add_component(db_session, activiteit.id, _onderdeel_gegevens(),
                                 actor="a@b.c")
    prod = service.add_product(db_session, activiteit.id, comp.id,
                               _product_gegevens(is_free=True), actor="a@b.c")

    with pytest.raises(service.ActiviteitFout):
        service.update_product(db_session, comp.id, prod.id, {"pay_on_site": True},
                               actor="a@b.c")


def test_een_product_van_een_ander_onderdeel_is_niet_te_raken(db_session):
    activiteit = service.create_activity(db_session, name="Twee", actor="a@b.c")
    a = service.add_component(db_session, activiteit.id, _onderdeel_gegevens("A"),
                              actor="a@b.c")
    b = service.add_component(db_session, activiteit.id, _onderdeel_gegevens("B"),
                              actor="a@b.c")
    prod = service.add_product(db_session, activiteit.id, a.id, _product_gegevens(),
                               actor="a@b.c")

    assert service.update_product(db_session, b.id, prod.id, {"name": "x"}) is None
    assert service.delete_product(db_session, b.id, prod.id) is False
    assert service.delete_product(db_session, a.id, prod.id) is True


def test_de_router_rekent_niet_meer_zelf(db_session):
    """De scheiding zelf: wat overblijft in de route is HTTP, geen domeinlogica."""
    bron = open("app/domains/activities/router.py", encoding="utf-8").read()
    for naam in ("def create_activity(", "def update_activity(", "def delete_activity(",
                 "def add_activity_date(", "def update_activity_date(",
                 "def delete_activity_date(",
                 "def add_component(", "def update_component(", "def delete_component(",
                 "def add_product(", "def update_product(", "def delete_product("):
        start = bron.index(naam)
        einde = bron.index("\n@router", start)
        body = bron[start:einde]
        assert "service." in body, f"{naam} roept de service niet aan"
        assert "snapshot_" not in body, (
            f"{naam} schrijft nog zelf geschiedenis — dat hoort in de service")
        assert "soft_delete(" not in body, (
            f"{naam} verwijdert nog zelf — dat hoort in de service")
