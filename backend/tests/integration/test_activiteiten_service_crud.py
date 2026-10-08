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

CR-13 phase 4b (#1251) removed the JSON routes, and with them the twelve service
functions only those routes called (creating an activity, and the single date,
component, product and order-line doors). Their tests went with them: the fiche
save and the registration screen's save have their own, in `test_fiche_save.py`,
`test_new_activity_on_fiche_1649.py` and the tests below. What is left here are
the service functions a screen still calls.
"""

import pytest

from app.domains.activities import service
from app.domains.activities.api import Activity, ActivityDate
from tests.conftest import add_order_line, register_at_the_door

pytestmark = pytest.mark.ui_agnostisch


def test_bijwerken_geeft_none_bij_een_onbekende_activiteit(db_session):
    """De service kent geen HTTP: de aanroeper beslist wat 'bestaat niet' betekent."""
    assert service.update_activity(db_session, 999999, {"name": "x"}) is None


def test_bijwerken_wijzigt_en_bewaart(db_session):
    from tests.conftest import seed_activity_with_product

    activiteit, _comp, _product = seed_activity_with_product(db_session)
    vers = service.update_activity(
        db_session, activiteit.id, {"name": "Nieuw", "location": "Elders"}, actor="a@b.c"
    )
    assert vers.name == "Nieuw" and vers.location == "Elders"


def test_verwijderen_neemt_de_boom_mee_maar_niet_de_betalingen(db_session):
    """Soft delete van datums, onderdelen, producten en inschrijvingen (#166).
    Betalingen blijven: financieel feit — dezelfde regel die #667 vastlegde."""
    from decimal import Decimal

    from app.domains.payment.api import PaymentRecord, get_records_for
    from tests.conftest import seed_activity_with_product

    activiteit, comp, product = seed_activity_with_product(db_session)
    db_session.add(
        PaymentRecord(
            payable_type="registration",
            payable_id=6790,
            amount=Decimal("10.00"),
            method="transfer",
            status="pending",
        )
    )
    db_session.commit()

    assert service.delete_activity(db_session, activiteit.id, actor="a@b.c") is True

    db_session.expire_all()
    assert db_session.query(Activity).filter(Activity.id == activiteit.id).first() is None
    assert (
        db_session.query(ActivityDate).filter(ActivityDate.activity_id == activiteit.id).count()
        == 0
    )
    # De betaling staat er nog.
    assert get_records_for(db_session, "registration", 6790)


def test_verwijderen_geeft_false_bij_een_onbekende_activiteit(db_session):
    assert service.delete_activity(db_session, 999999) is False


# ── Batch 4 en 5: bestelregels, inschrijvingen, export ────────────────────────


def _inschrijving_met_regel(client, db, aantal=2):
    from tests.conftest import seed_activity_with_product

    activity, comp, product = seed_activity_with_product(db, price="10.00")
    resp = register_at_the_door(
        client,
        activity.id,
        json={
            "contact_name": "An",
            "phone": "0470000000",
            "contact_email": "an@example.com",
            "component_id": comp.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": aantal}],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    from app.domains.activities.api import Registration

    reg = db.query(Registration).filter(Registration.id == resp.json()["id"]).one()
    return activity, comp, product, reg


def test_een_bestelregel_toevoegen_herrekent_het_saldo(client, db_session):
    """De reconciliatie hoort bij de mutatie: wie de bestelling bewaart zoals het
    inschrijvingsscherm (`set_order_quantities`), krijgt het saldo herrekend."""
    from decimal import Decimal

    from tests._invarianten import assert_saldo_klopt

    activity, comp, product, reg = _inschrijving_met_regel(client, db_session, aantal=1)
    add_order_line(db_session, activity.id, reg.id, product.id, 2)

    db_session.expire_all()
    assert_saldo_klopt(db_session, "registration", reg.id, Decimal("30.00"))


def test_hetzelfde_product_hoogt_op_in_plaats_van_te_verdubbelen(client, db_session):
    """#197: geen tweede regel voor hetzelfde product."""
    activity, comp, product, reg = _inschrijving_met_regel(client, db_session, aantal=1)
    add_order_line(db_session, activity.id, reg.id, product.id, 2)

    db_session.expire_all()
    db_session.refresh(reg)
    regels = [i for i in reg.items if i.product_id == product.id]
    assert len(regels) == 1 and regels[0].quantity == 3


def test_een_negatief_aantal_is_een_domeinfout(client, db_session):
    """Nul is op het scherm "niet gekozen" en haalt de regel weg; onder nul bestaat niet."""
    activity, comp, product, reg = _inschrijving_met_regel(client, db_session)
    with pytest.raises(service.ActiviteitFout, match="niet negatief"):
        service.set_order_quantities(db_session, activity.id, reg.id, {product.id: -1})
    db_session.expire_all()
    assert [i.quantity for i in reg.items] == [2]


def test_een_product_van_een_andere_activiteit_wordt_geweigerd(client, db_session):
    """De koppeling inschrijving ↔ aanbod is een domeinregel."""
    from tests.conftest import seed_activity_with_product

    activity, comp, product, reg = _inschrijving_met_regel(client, db_session)
    _andere, _c, vreemd = seed_activity_with_product(db_session)

    with pytest.raises(service.ActiviteitFout, match="hoort niet bij deze activiteit"):
        service.set_order_quantities(db_session, activity.id, reg.id, {vreemd.id: 1})
    db_session.expire_all()
    assert [i.product_id for i in reg.items] == [product.id]


def test_een_inschrijving_verwijderen_laat_de_betaling_staan(client, db_session):
    """#190/#313: de bestelregels gaan mee, het financiële feit blijft."""
    from app.domains.payment.api import get_records_for

    activity, comp, product, reg = _inschrijving_met_regel(client, db_session)
    assert service.delete_registration(db_session, activity.id, reg.id, actor="a@b.c") is True

    db_session.expire_all()
    from app.domains.activities.api import Registration

    assert db_session.query(Registration).filter(Registration.id == reg.id).first() is None
    assert get_records_for(db_session, "registration", reg.id) is not None


def test_alleen_een_echte_wijziging_komt_in_het_logboek(client, db_session):
    """Een opslag zonder verschil hoort geen rij in de geschiedenis op te leveren."""
    from app.domains.activities.api import RegistrationHistory

    activity, comp, product, reg = _inschrijving_met_regel(client, db_session)
    voor = (
        db_session.query(RegistrationHistory)
        .filter(RegistrationHistory.registration_id == reg.id)
        .count()
    )

    service.update_registration_contact(
        db_session, activity.id, reg.id, {"contact_name": "An"}, actor="a@b.c"
    )
    db_session.expire_all()
    na = (
        db_session.query(RegistrationHistory)
        .filter(RegistrationHistory.registration_id == reg.id)
        .count()
    )
    assert na == voor, "een opslag zonder verschil schreef toch geschiedenis"

    service.update_registration_contact(
        db_session, activity.id, reg.id, {"contact_name": "Anneke"}, actor="a@b.c"
    )
    db_session.expire_all()
    assert (
        db_session.query(RegistrationHistory)
        .filter(RegistrationHistory.registration_id == reg.id)
        .count()
        == voor + 1
    )


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
    assert service.registrations_for(db_session, activity.id, without_component=True) == []
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
        "in `activities/service.py` te staan (#679)"
    )
    assert "admin_user_by_email" not in bron, (
        "de actor is het e-mailadres uit de sessie; een User-rij opzoeken om er "
        "`.email` van te lezen is een omweg langs de JSON-deurwachter"
    )


def test_de_laag_gate_heeft_geen_uitzonderingen_meer(db_session):
    """#679 is pas af als de allowlist leeg is — anders staat de gate groen om de
    verkeerde reden."""
    from tests.test_layer_gate import LAYER_ALLOWLIST

    assert LAYER_ALLOWLIST == set(), (
        f"de laag-gate draagt weer uitzonderingen: {sorted(LAYER_ALLOWLIST)}. "
        "Een uitzondering hoort tijdelijk te zijn en een issuenummer te dragen."
    )
