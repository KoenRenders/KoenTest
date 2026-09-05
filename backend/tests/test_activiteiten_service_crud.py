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


# ── Batch 4 en 5: bestelregels, inschrijvingen, export ────────────────────────

def _inschrijving_met_regel(client, db, aantal=2):
    from tests.conftest import seed_activity_with_product

    activity, comp, product = seed_activity_with_product(db, price="10.00")
    resp = client.post(f"/api/v1/activities/{activity.id}/register", json={
        "contact_name": "An", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": aantal}]})
    assert resp.status_code in (200, 201), resp.text
    from app.domains.activities.api import Registration
    reg = db.query(Registration).filter(Registration.id == resp.json()["id"]).one()
    return activity, comp, product, reg


def test_een_bestelregel_toevoegen_herrekent_het_saldo(client, db_session):
    """De reconciliatie hoort bij de mutatie, niet bij de responsvorm.

    Stond ze in de router-helper, dan laat een scherm dat de service rechtstreeks
    aanroept het saldo stil verkeerd staan.
    """
    from decimal import Decimal

    from tests._invarianten import assert_saldo_klopt

    activity, comp, product, reg = _inschrijving_met_regel(client, db_session, aantal=1)
    service.add_order_line(db_session, activity.id, reg.id, product.id, 2,
                           actor="a@b.c")

    db_session.expire_all()
    assert_saldo_klopt(db_session, "registration", reg.id, Decimal("30.00"))


def test_hetzelfde_product_hoogt_op_in_plaats_van_te_verdubbelen(client, db_session):
    """#197: geen tweede regel voor hetzelfde product."""
    activity, comp, product, reg = _inschrijving_met_regel(client, db_session, aantal=1)
    service.add_order_line(db_session, activity.id, reg.id, product.id, 2,
                           actor="a@b.c")

    db_session.expire_all()
    db_session.refresh(reg)
    regels = [i for i in reg.items if i.product_id == product.id]
    assert len(regels) == 1 and regels[0].quantity == 3


def test_een_aantal_onder_een_is_een_domeinfout(client, db_session):
    activity, comp, product, reg = _inschrijving_met_regel(client, db_session)
    with pytest.raises(service.ActiviteitFout):
        service.add_order_line(db_session, activity.id, reg.id, product.id, 0)


def test_een_product_van_een_andere_activiteit_wordt_geweigerd(client, db_session):
    """De koppeling inschrijving ↔ aanbod is een domeinregel."""
    from tests.conftest import seed_activity_with_product

    activity, comp, product, reg = _inschrijving_met_regel(client, db_session)
    _andere, _c, vreemd = seed_activity_with_product(db_session)

    with pytest.raises(service.ActiviteitFout):
        service.add_order_line(db_session, activity.id, reg.id, vreemd.id, 1)


def test_een_inschrijving_verwijderen_laat_de_betaling_staan(client, db_session):
    """#190/#313: de bestelregels gaan mee, het financiële feit blijft."""
    from app.domains.payment.api import get_records_for

    activity, comp, product, reg = _inschrijving_met_regel(client, db_session)
    assert service.delete_registration(db_session, activity.id, reg.id,
                                       actor="a@b.c") is True

    db_session.expire_all()
    from app.domains.activities.api import Registration
    assert db_session.query(Registration).filter(
        Registration.id == reg.id).first() is None
    assert get_records_for(db_session, "registration", reg.id) is not None


def test_alleen_een_echte_wijziging_komt_in_het_logboek(client, db_session):
    """Een opslag zonder verschil hoort geen rij in de geschiedenis op te leveren."""
    from app.domains.activities.api import RegistrationHistory

    activity, comp, product, reg = _inschrijving_met_regel(client, db_session)
    voor = db_session.query(RegistrationHistory).filter(
        RegistrationHistory.registration_id == reg.id).count()

    service.update_registration_contact(db_session, activity.id, reg.id,
                                        {"contact_name": "An"}, actor="a@b.c")
    db_session.expire_all()
    na = db_session.query(RegistrationHistory).filter(
        RegistrationHistory.registration_id == reg.id).count()
    assert na == voor, "een opslag zonder verschil schreef toch geschiedenis"

    service.update_registration_contact(db_session, activity.id, reg.id,
                                        {"contact_name": "Anneke"}, actor="a@b.c")
    db_session.expire_all()
    assert db_session.query(RegistrationHistory).filter(
        RegistrationHistory.registration_id == reg.id).count() == voor + 1


def test_de_export_levert_inhoud_en_een_veilige_bestandsnaam(client, db_session):
    """De opbouw stond al in export.py; het opzoeken en de naam kwamen erbij."""
    activity, comp, product, reg = _inschrijving_met_regel(client, db_session)
    activity.name = "Ge/kke naam: 2026"
    db_session.commit()

    resultaat = service.component_export(db_session, activity.id, comp.id)
    assert resultaat is not None
    inhoud, naam = resultaat
    assert inhoud and naam.endswith(".ods")
    assert "/" not in naam and ":" not in naam, f"onveilige bestandsnaam: {naam}"

    assert service.component_export(db_session, activity.id, 999999) is None


def test_de_router_rekent_niet_meer_zelf(db_session):
    """De scheiding zelf: wat overblijft in de route is HTTP, geen domeinlogica."""
    bron = open("app/domains/activities/router.py", encoding="utf-8").read()
    for naam in ("def create_activity(", "def update_activity(", "def delete_activity(",
                 "def add_activity_date(", "def update_activity_date(",
                 "def delete_activity_date(",
                 "def add_component(", "def update_component(", "def delete_component(",
                 "def add_product(", "def update_product(", "def delete_product(",
                 "def add_order_line(", "def update_order_line(",
                 "def delete_order_line(", "def delete_registration(",
                 "def update_registration_remarks(", "def export_component_ods("):
        start = bron.index(naam)
        einde = bron.index("\n@router", start)
        body = bron[start:einde]
        assert "service." in body, f"{naam} roept de service niet aan"
        assert "snapshot_" not in body, (
            f"{naam} schrijft nog zelf geschiedenis — dat hoort in de service")
        assert "soft_delete(" not in body, (
            f"{naam} verwijdert nog zelf — dat hoort in de service")


# ── Batch 6: het scherm gaat rechtstreeks naar de service ─────────────────────

def test_inschrijvingen_ophalen_werkt_zonder_de_router(client, db_session):
    """De laatste twee leesbewerkingen die `admin_ui` nog uit de router haalde."""
    activity, comp, product, reg = _inschrijving_met_regel(client, db_session)

    alle = service.registrations_for(db_session, activity.id, component_id=comp.id)
    assert alle is not None and [r["id"] for r in alle] == [reg.id]
    regel = alle[0]["items"][0]
    assert regel["product_name"] == product.name
    assert regel["component_name"] == comp.name

    # Zonder onderdeel is een ándere vraag dan "alle" (#650): deze inschrijving
    # hangt aan een onderdeel en hoort er dus niet bij.
    assert service.registrations_for(db_session, activity.id,
                                     without_component=True) == []
    assert service.registrations_for(db_session, 999999) is None


def test_het_activiteitenbeheer_gaat_niet_meer_via_de_router(db_session):
    """De reden dat de laag-gate leeg mag: geen enkel scherm importeert de router.

    Deze test kijkt naar `admin_ui` bij naam. De gate scant álle UI-modules en zou
    hier ook op afgaan, maar juist daarom staat het hier nog eens expliciet: dit
    bestand was de laatste uitzondering, en wie ze terugzet moet twee tests rood
    zien, niet één.
    """
    bron = open("app/domains/activities/admin_ui.py", encoding="utf-8").read()
    assert "activities.router" not in bron, (
        "het activiteitenbeheer haalt weer een bewerking uit de router; die hoort "
        "in `activities/service.py` te staan (#679)")
    assert "admin_user_by_email" not in bron, (
        "de actor is het e-mailadres uit de sessie; een User-rij opzoeken om er "
        "`.email` van te lezen is een omweg langs de JSON-deurwachter")


def test_de_laag_gate_heeft_geen_uitzonderingen_meer(db_session):
    """#679 is pas af als de allowlist leeg is — anders staat de gate groen om de
    verkeerde reden."""
    from tests.test_layer_gate import LAYER_ALLOWLIST

    assert LAYER_ALLOWLIST == set(), (
        f"de laag-gate draagt weer uitzonderingen: {sorted(LAYER_ALLOWLIST)}. "
        "Een uitzondering hoort tijdelijk te zijn en een issuenummer te dragen.")
