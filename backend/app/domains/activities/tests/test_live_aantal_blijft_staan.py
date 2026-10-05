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

**Sinds #1613 bevat het antwoord van `/totaal` geen veld meer** — alleen het
totaal. Het kan een getypt aantal dus niet meer terugzetten; de eerste test eist
precies dat, en de derde stuurt bij Opslaan mee wat in het (nooit vervangen)
veld staat. Het oude antwoord tekende het hele paneel opnieuw uit de bewaarde
inschrijving en zette daarmee ook een getypte naam of opmerking terug
(`tests_e2e/test_registration_edit_keeps_typing.py`).

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (lokaal): de
getypte aantallen uit `counts = {**stored, **(quantities or {})}` in `_detail_ctx`
weggehaald (#1494, de velden heten sindsdien `product_<id>`) → de eerste en de
derde test vallen om; de tweede (zonder quantities) blijft groen, want die hangt
aan de andere kant van de voorwaarde.
"""

import re

import pytest

from app.domains.activities.api import RegistrationItem
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return {"X-CSRF-Token": csrf_token_for(waarde)}


def _inschrijving(client, db, aantal=2):
    activity, comp, product = seed_activity_with_product(db, is_free=False)
    resp = client.post(
        f"/api/v1/activities/{activity.id}/register",
        json={
            "contact_name": "An Janssens",
            "phone": "0470000000",
            "contact_email": "an@example.com",
            "component_id": comp.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": aantal}],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    reg_id = resp.json()["id"]
    item_id = db.query(RegistrationItem).filter(RegistrationItem.registration_id == reg_id).one().id
    return reg_id, item_id, product.id


def _veldwaarde(html: str, product_id: int) -> str:
    """De `value` van het aantal-veld uit het antwoord vissen.

    Op de tag zelf en niet op "1× Testproduct": die leesregel staat in het
    dichtgeklapte deel en toont iets anders dan het invoerveld — precies het
    verschil waar deze bug over gaat.
    """
    tag = re.search(rf'<input[^>]*name="product_{product_id}"[^>]*>', html)
    assert tag, "het aantal-veld staat niet in het antwoord"
    waarde = re.search(r'value="([^"]*)"', tag.group(0))
    assert waarde, f"het veld heeft geen value: {tag.group(0)}"
    return waarde.group(1)


def test_het_antwoord_zet_geen_aantal_terug(client, db_session):
    """Het gemelde geval: 2 → 1. Het antwoord rekent met 1 en bevat geen veld:
    wat in het veld staat, blijft staan (#1613)."""
    reg_id, item_id, product_id = _inschrijving(client, db_session, aantal=2)
    hdr = _login(client)

    resp = client.post(
        f"/admin/inschrijvingen/{reg_id}/totaal", headers=hdr, data={f"product_{product_id}": "1"}
    )

    assert resp.status_code == 200, resp.text
    assert "<input" not in resp.text, "het antwoord bevat een veld en kan het dus terugzetten"
    assert "Totaal: € 10,00" in resp.text, "het totaal rekent niet met het getypte aantal"


def test_zonder_getypt_aantal_blijft_de_bewaarde_stand_staan(client, db_session):
    """De tegenhanger: het gewone openen van het paneel toont wat er bewaard is.

    Zonder haar zou "neem altijd wat er binnenkomt" ook groen staan, en dan toont
    een vers geopend paneel een leeg of nul-aantal.
    """
    reg_id, item_id, product_id = _inschrijving(client, db_session, aantal=2)
    hdr = _login(client)

    resp = client.get(f"/admin/inschrijvingen/{reg_id}", headers=hdr)

    assert _veldwaarde(resp.text, product_id) == "2"


def test_na_totaal_bewaart_opslaan_het_nieuwe_aantal(client, db_session):
    """De volledige weg, en dit is waar het geld zit.

    /totaal → /opslaan met precies wat het formulier terugstuurt. Ging het veld
    terug naar 2, dan stuurt Opslaan 2 mee, ziet de route geen verschil en bewaart
    ze niets — de wijziging verdwijnt zonder melding.
    """
    reg_id, item_id, product_id = _inschrijving(client, db_session, aantal=2)
    hdr = _login(client)

    live = client.post(
        f"/admin/inschrijvingen/{reg_id}/totaal", headers=hdr, data={f"product_{product_id}": "1"}
    )
    # #1613: the answer carries no field, so the form still holds the typed 1.
    assert "<input" not in live.text
    teruggestuurd = "1"

    opslaan = client.post(
        f"/admin/inschrijvingen/{reg_id}/opslaan",
        headers=hdr,
        data={
            "contact_name": "An Janssens",
            "phone": "0470000000",
            "contact_email": "an@example.com",
            "remarks": "",
            f"product_{product_id}": teruggestuurd,
        },
    )
    assert opslaan.status_code == 200, opslaan.text

    db_session.expire_all()
    assert db_session.get(RegistrationItem, item_id).quantity == 1, (
        "het formulier stuurde de teruggezette waarde mee en er is niets bewaard"
    )


def test_het_live_endpoint_bewaart_nog_steeds_niets(client, db_session):
    """#613-2 mag hier niet sneuvelen: er is één "Opslaan", geen autosave."""
    reg_id, item_id, product_id = _inschrijving(client, db_session, aantal=2)
    hdr = _login(client)

    client.post(
        f"/admin/inschrijvingen/{reg_id}/totaal", headers=hdr, data={f"product_{product_id}": "1"}
    )

    db_session.expire_all()
    assert db_session.get(RegistrationItem, item_id).quantity == 2, (
        "/totaal heeft stilletjes opgeslagen"
    )
