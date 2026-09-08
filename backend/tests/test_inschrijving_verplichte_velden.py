"""#733 — het formulier belóófde vier verplichte velden, de server dwong er één af.

Het `required`-attribuut is vorm, geen betekenis: het geldt alleen voor wie het
formulier in een browser invult. `POST /api/v1/activities/{id}/register` kwam er
zonder mobiel nummer of ploegnaam gewoon door, en via het beheerscherm kon je naam,
mobiel én ploegnaam achteraf leegmaken.

| veld | vóór #733 |
|---|---|
| naam | `contact_name: str` — `""` kwam erdoor |
| e-mailadres | `EmailStr` — als enige écht gevalideerd |
| mobiel nummer | `Optional[str] = None` |
| ploegnaam | `Optional[str] = None`, ook als het onderdeel er een vroeg |

**Waarom de laatste twee tests er staan.** Zonder hen zou "weiger alles" ook groen
zijn — en dan kan een beheerder een tikfout niet meer rechtzetten (#624/#716) en
kan een ploegnaam nergens meer leeg, ook niet waar het onderdeel er geen vraagt.
Een test die alleen weigeringen toetst, keurt een kapot scherm goed.

De ploegnaamregel hangt aan de HUIDIGE configuratie van het onderdeel en niet aan
de geschiedenis van de rij: vraagt het onderdeel er een, dan hoort ze er te zijn,
ook bij een oude inschrijving die er nog geen had. Koens keuze (8 sep 2026); de
prijs is dat zo'n oude inschrijving eerst een ploegnaam nodig heeft voor je iets
anders kan corrigeren, en op PROD raakt dat nul rijen.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (lokaal):
  * `controleer_inschrijfvelden` leeggemaakt (`return` als eerste regel) → alle
    zeven weigertests vallen om (vier op de API, drie op het beheerscherm) en de
    drie tegenproeven blijven groen;
  * alleen de aanroep in `register_for_activity` weggehaald → precies de vier
    API-tests vallen om en die van het beheerscherm niet. Dat verschil is het gat
    dat dit issue dicht: het HTML-attribuut raakte dat pad nooit.
"""
import pytest

from app.domains.activities.api import Registration
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_agnostisch


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return {"X-CSRF-Token": csrf_token_for(waarde)}


def _opzet(db, *, vraagt_ploegnaam=True):
    activity, comp, product = seed_activity_with_product(db, is_free=False)
    comp.team_name_required = vraagt_ploegnaam
    db.flush()
    return activity, comp, product


def _payload(comp, product, **overschrijf):
    basis = {"contact_name": "An Janssens", "contact_email": "an@example.com",
             "phone": "0470000000", "team_name": "A-team",
             "component_id": comp.id, "payment_method": "TRANSFER",
             "items": [{"product_id": product.id, "quantity": 1}]}
    basis.update(overschrijf)
    return basis


def _inschrijven(client, activity, payload):
    return client.post(f"/api/v1/activities/{activity.id}/register", json=payload)


# ── De JSON-API: hier raakte het HTML-attribuut nooit ────────────────────────

@pytest.mark.parametrize("weggelaten", ["contact_name", "phone", "team_name"])
def test_de_api_weigert_een_leeg_verplicht_veld(client, db_session, weggelaten):
    """Elk veld apart, en telkens als PAAR met de geslaagde variant hieronder.

    Toetsen op "een 422" alleen zou niets bewijzen: een ontbrekend ander veld geeft
    er ook een. Daarom is het verschil met de volledige payload het bewijs.
    """
    activity, comp, product = _opzet(db_session)

    zonder = _inschrijven(client, activity, _payload(comp, product, **{weggelaten: ""}))
    assert zonder.status_code == 422, zonder.text
    assert not db_session.query(Registration).filter(
        Registration.activity_id == activity.id).all(), (
        "een geweigerde inschrijving mag niets aanmaken")

    met = _inschrijven(client, activity, _payload(comp, product))
    assert met.status_code in (200, 201), met.text


def test_de_api_weigert_een_ontbrekend_veld_net_zo_goed(client, db_session):
    """Weglaten is niet hetzelfde als leegsturen: `phone` en `team_name` hadden een
    default van None, dus ze kwamen er zonder sleutel gewoon door."""
    activity, comp, product = _opzet(db_session)
    payload = _payload(comp, product)
    payload.pop("phone")

    assert _inschrijven(client, activity, payload).status_code == 422


# ── Het beheerscherm: leegmaken achteraf ─────────────────────────────────────

@pytest.mark.parametrize("veld", ["contact_name", "phone", "team_name"])
def test_het_bewerkscherm_weigert_leegmaken(client, db_session, veld):
    """En het toont waarom, in de foutbanner — geen kale 422 (#723).

    htmx swapt een 4xx niet, dus een 422 zou hier betekenen dat er op het scherm
    niets gebeurt. Vandaar 200 mét banner.
    """
    activity, comp, product = _opzet(db_session)
    aangemaakt = _inschrijven(client, activity, _payload(comp, product))
    reg_id = aangemaakt.json()["id"]
    hdr = _login(client)
    velden = {"contact_name": "An Janssens", "contact_email": "an@example.com",
              "phone": "0470000000", "team_name": "A-team", "remarks": ""}

    resp = client.post(f"/admin/inschrijvingen/{reg_id}/opslaan", headers=hdr,
                       data={**velden, veld: "   "})

    assert resp.status_code == 200, resp.text
    assert 'role="alert"' in resp.text, "de melding staat niet in de foutbanner"
    db_session.expire_all()
    assert getattr(db_session.get(Registration, reg_id), veld) is not None, (
        "de weigering mag niets wegschrijven")


# ── De tegenproeven: zonder deze keurt de suite een kapot scherm goed ────────

def test_wijzigen_naar_een_andere_waarde_blijft_werken(client, db_session):
    """#624 en #716: een tikfout moet rechtgezet kunnen worden."""
    activity, comp, product = _opzet(db_session)
    reg_id = _inschrijven(client, activity, _payload(comp, product)).json()["id"]
    hdr = _login(client)

    resp = client.post(f"/admin/inschrijvingen/{reg_id}/opslaan", headers=hdr, data={
        "contact_name": "An Peeters", "contact_email": "juist@example.com",
        "phone": "0471111111", "team_name": "B-team", "remarks": ""})
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    reg = db_session.get(Registration, reg_id)
    assert (reg.contact_name, reg.phone, reg.team_name) == (
        "An Peeters", "0471111111", "B-team")


def test_zonder_de_vlag_mag_de_ploegnaam_wel_leeg(client, db_session):
    """De regel hangt aan het onderdeel. Vraagt het er geen, dan is een lege
    ploegnaam gewoon geen ploegnaam."""
    activity, comp, product = _opzet(db_session, vraagt_ploegnaam=False)
    reg_id = _inschrijven(client, activity,
                          _payload(comp, product)).json()["id"]
    hdr = _login(client)

    resp = client.post(f"/admin/inschrijvingen/{reg_id}/opslaan", headers=hdr, data={
        "contact_name": "An Janssens", "contact_email": "an@example.com",
        "phone": "0470000000", "team_name": "   ", "remarks": ""})
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    assert db_session.get(Registration, reg_id).team_name is None


def test_zonder_de_vlag_mag_de_ploegnaam_ook_ontbreken_bij_het_aanmaken(client,
                                                                        db_session):
    """De spiegelbeeld-tegenproef op de API-kant."""
    activity, comp, product = _opzet(db_session, vraagt_ploegnaam=False)
    payload = _payload(comp, product)
    payload.pop("team_name")

    assert _inschrijven(client, activity, payload).status_code in (200, 201)
