"""#676 — de inschrijvingenlijst per onderdeel: toggle, omkadering, één weergave.

Vervolg op #650. Drie dingen tegelijk:

1. De lijst begon zonder kop of scheiding, direct ná het productenpaneel, en las
   daardoor als een vervolg van de producten.
2. De knop was een kale `hx-get`: geen open/dicht-toestand, dus opnieuw klikken
   haalde hetzelfde nog eens op en je kreeg de lijst niet meer weg.
3. Het detailpaneel verdubbelde de rij. `_inschrijving_detail.html` is een
   ZELFSTANDIGE weergave — naam, contact, producten, opmerking én een eigen
   bewerk-toggle. Dat is correct voor het betalingenscherm, waar het de enige
   weergave van die inschrijving is. Naast een rij die hetzelfde toont, staan er
   twee leesweergaven van één ding, elk met hun eigen bewerkstand: precies de
   dubbele toestand die #648 wegnam.

Gekozen: de rij wijkt voor het paneel (§2.8, zoals de betaalkaart). Het alternatief
— de rij compact maken — laat twee leesweergaven bestaan en dus twee bewerkstanden.
"""
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _met_inschrijving(client, db):
    activity, comp, product = seed_activity_with_product(db, price="10.00")
    resp = client.post(f"/api/v1/activities/{activity.id}/register", json={
        "contact_name": "An Janssens", "phone": "0470000000", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "remarks": "Komt wat later toe",
        "items": [{"product_id": product.id, "quantity": 2}]})
    assert resp.status_code in (200, 201), resp.text
    return activity, comp, resp.json()["id"]


def test_de_toonknop_is_een_toggle_met_toestand(client, db_session):
    activity, comp, _reg = _met_inschrijving(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text

    assert "Toon inschrijvingen" in html and "Verberg inschrijvingen" in html, (
        "de knop volgt de toestand niet")
    assert ':aria-expanded="insch"' in html, "de knop meldt zijn stand niet"
    # Eén keer laden: opnieuw klikken hoort te sluiten, niet opnieuw op te halen.
    knopblok = html[html.index("Toon inschrijvingen") - 600:html.index("Toon inschrijvingen")]
    assert 'hx-trigger="click once"' in knopblok


def test_de_lijst_staat_in_een_eigen_omkaderd_blok(client, db_session):
    """Zonder kop las ze als een vervolg van de producten."""
    activity, comp, _reg = _met_inschrijving(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text

    blok = html[html.index(f'id="aa-insch-{comp.id}"') - 900:]
    blok = blok[:blok.index(f'id="aa-insch-{comp.id}"') + 100]
    assert "Inschrijvingen" in blok, "het blok heeft geen eigen kop"


def test_geen_inline_paneel_meer(client, db_session):
    """Herzien op de feedbackronde van 15 sep (golf 8): het inline openvouwen
    (#510/#676) verdween uit deze lijst — de rij-knop "Bewerken" opent de
    inschrijvingspagina meteen in bewerkmodus. De oude zorg (twee leesweergaven
    van hetzelfde, #648) kan dus niet terugkomen via een paneel dat er niet is.
    """
    activity, comp, _reg = _met_inschrijving(client, db_session)
    _login(client)
    html = client.get(
        f"/admin/activiteiten/{activity.id}/onderdelen/{comp.id}/inschrijvingen").text

    assert 'x-show="!open"' not in html and 'x-show="open"' not in html, (
        "het inline paneel is terug — de feedbackronde van 15 sep haalde het weg")
    assert "detail_disclosure" not in html


def test_de_rijknop_heet_bewerken_en_opent_de_bewerkstand(client, db_session):
    """Eén klik naar het bewerkscherm (feedbackronde 15 sep): de rij-knop heet
    "Bewerken" en de pagina waar hij op landt opent mét de editor open. #676
    ("Details, want de rijknop bewerkt niets") is daarmee herroepen: de knop
    bewerkt nu wél — hij landt op het bewerkscherm zelf."""
    activity, comp, reg = _met_inschrijving(client, db_session)
    _login(client)
    html = client.get(
        f"/admin/activiteiten/{activity.id}/onderdelen/{comp.id}/inschrijvingen").text

    assert ">Bewerken<" in html
    assert ">Details<" not in html and ">Verwijderen<" not in html
    pagina = client.get(f"/admin/inschrijvingen/{reg}?bewerk=1").text
    assert "{ edit: true }" in pagina, "bewerk=1 opent de pagina niet in bewerkmodus"


def test_de_macro_belooft_geen_bewerken_meer():
    """De wortel van de naamsverwarring: detail_disclosure vouwt open, ze bewerkt
    niets. De enige aanroeper gaf zijn label al mee, dus dit raakt vandaag niets."""
    kit = open("app/ui/templates/_macros.html", encoding="utf-8").read()
    macro = kit[kit.index("{% macro detail_disclosure("):]
    macro = macro[:macro.index("{%- endmacro %}")]
    assert 'label or _("Details")' in macro


def test_het_paneel_heeft_een_bewerkstand(client, db_session):
    """Eén bewerk-toggle, van het paneel zelf.

    Niet tellen hoe vaak de naam voorkomt: die staat terecht twee keer — als
    leesregel én als waarde in het invulveld eronder. Dat is de normale vorm van
    een paneel met een lees- en een bewerkstand; de dubbeling die #676 wegneemt
    zat tussen de RIJ en het paneel, niet binnen het paneel.
    """
    _activity, _comp, reg_id = _met_inschrijving(client, db_session)
    _login(client)
    paneel = client.get(f"/admin/inschrijvingen/{reg_id}").text

    # Kop-herziening golf 6 (#913): de opener draagt x-show="!edit" op de knop
    # zelf (klasse ertussen), met het cluster ernaast als bewerkstand.
    import re as _re
    assert len(_re.findall(r'<button[^>]*x-show="!edit"[^>]*>Bewerken</button>', paneel)) == 1
    # Leesregel én invulveld: precies één van elk.
    assert paneel.count('value="An Janssens"') == 1
    assert "An Janssens" in paneel
