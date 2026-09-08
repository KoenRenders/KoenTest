"""#732 — het getypte aantal sprong terug terwijl de bedragen meegingen.

Zet je in het bewerkpaneel een aantal van 2 naar 1, dan vervangt `/totaal` het hele
paneel — inclusief het veld waarin je net typte. Dat antwoord rekende wél met 1
(de bedragen klopten) maar rendeerde het invoerveld met de **bewaarde** 2.

Het gevolg is erger dan het beeld: bij Opslaan stuurt het formulier die
teruggezette 2 mee, `inschrijving_opslaan` ziet geen verschil met de bewaarde
waarde en bewaart niets. De wijziging verdwijnt zonder melding.

**Een test op het totaal staat hier groen mét de bug erin** — dat totaal klopte al.
Er wordt daarom getoetst op de waarde van het invoerveld in het antwoord, en op wat
er na de volledige weg `/totaal` → `/opslaan` in de databank staat.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (lokaal): de
regel `regel["quantity"] = quantities[regel["id"]]` weggehaald → de eerste en de
derde test vallen om; de tweede (zonder quantities) blijft groen, want die hangt
aan de andere kant van de voorwaarde.
"""
import re

import pytest

from app.domains.activities.api import Registration, RegistrationItem
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return {"X-CSRF-Token": csrf_token_for(waarde)}


def _inschrijving(client, db, aantal=2):
    activity, comp, product = seed_activity_with_product(db, is_free=False)
    resp = client.post(f"/api/v1/activities/{activity.id}/register", json={
        "contact_name": "An Janssens", "phone": "0470000000", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": aantal}]})
    assert resp.status_code in (200, 201), resp.text
    reg_id = resp.json()["id"]
    item_id = (db.query(RegistrationItem)
               .filter(RegistrationItem.registration_id == reg_id).one().id)
    return reg_id, item_id


def _veldwaarde(html: str, item_id: int) -> str:
    """De `value` van het aantal-veld uit het antwoord vissen.

    Op de tag zelf en niet op "1× Testproduct": die leesregel staat in het
    dichtgeklapte deel en toont iets anders dan het invoerveld — precies het
    verschil waar deze bug over gaat.
    """
    tag = re.search(rf'<input[^>]*name="quantity_{item_id}"[^>]*>', html)
    assert tag, "het aantal-veld staat niet in het antwoord"
    waarde = re.search(r'value="([^"]*)"', tag.group(0))
    assert waarde, f"het veld heeft geen value: {tag.group(0)}"
    return waarde.group(1)


def test_het_getypte_aantal_komt_terug_in_het_veld(client, db_session):
    """Het gemelde geval: 2 → 1."""
    reg_id, item_id = _inschrijving(client, db_session, aantal=2)
    hdr = _login(client)

    resp = client.post(f"/admin/inschrijvingen/{reg_id}/totaal", headers=hdr,
                       data={f"quantity_{item_id}": "1"})

    assert resp.status_code == 200, resp.text
    assert _veldwaarde(resp.text, item_id) == "1", (
        "het veld springt terug op de bewaarde waarde terwijl de bedragen die van "
        "het getypte aantal tonen")


def test_zonder_getypt_aantal_blijft_de_bewaarde_stand_staan(client, db_session):
    """De tegenhanger: het gewone openen van het paneel toont wat er bewaard is.

    Zonder haar zou "neem altijd wat er binnenkomt" ook groen staan, en dan toont
    een vers geopend paneel een leeg of nul-aantal.
    """
    reg_id, item_id = _inschrijving(client, db_session, aantal=2)
    hdr = _login(client)

    resp = client.get(f"/admin/inschrijvingen/{reg_id}", headers=hdr)

    assert _veldwaarde(resp.text, item_id) == "2"


def test_na_totaal_bewaart_opslaan_het_nieuwe_aantal(client, db_session):
    """De volledige weg, en dit is waar het geld zit.

    /totaal → /opslaan met precies wat het formulier terugstuurt. Ging het veld
    terug naar 2, dan stuurt Opslaan 2 mee, ziet de route geen verschil en bewaart
    ze niets — de wijziging verdwijnt zonder melding.
    """
    reg_id, item_id = _inschrijving(client, db_session, aantal=2)
    hdr = _login(client)

    live = client.post(f"/admin/inschrijvingen/{reg_id}/totaal", headers=hdr,
                       data={f"quantity_{item_id}": "1"})
    teruggestuurd = _veldwaarde(live.text, item_id)

    opslaan = client.post(f"/admin/inschrijvingen/{reg_id}/opslaan", headers=hdr, data={
        "contact_name": "An Janssens", "phone": "0470000000", "contact_email": "an@example.com",
        "remarks": "", f"quantity_{item_id}": teruggestuurd})
    assert opslaan.status_code == 200, opslaan.text

    db_session.expire_all()
    assert db_session.get(RegistrationItem, item_id).quantity == 1, (
        "het formulier stuurde de teruggezette waarde mee en er is niets bewaard")


def test_het_live_endpoint_bewaart_nog_steeds_niets(client, db_session):
    """#613-2 mag hier niet sneuvelen: er is één "Opslaan", geen autosave."""
    reg_id, item_id = _inschrijving(client, db_session, aantal=2)
    hdr = _login(client)

    client.post(f"/admin/inschrijvingen/{reg_id}/totaal", headers=hdr,
                data={f"quantity_{item_id}": "1"})

    db_session.expire_all()
    assert db_session.get(RegistrationItem, item_id).quantity == 2, (
        "/totaal heeft stilletjes opgeslagen")
