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


def test_het_overzicht_heeft_geen_toonknop_meer(client, db_session):
    """Ronde 2 van de golf 8-feedback (15 sep): Toon inschrijvingen verhuisde
    naar de Inschrijvingen-tab; het Overzicht draagt de knop niet meer."""
    activity, comp, _reg = _met_inschrijving(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "Toon inschrijvingen" not in html
    assert "aa-insch-" not in html


def test_de_groep_is_dichtklapbaar_met_toestand(client, db_session):
    """De open/dichtklap van de groepen (ronde 2) meldt zijn stand, zoals de
    oude toonknop dat deed (§toegankelijkheid)."""
    activity, comp, _reg = _met_inschrijving(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen").text
    assert ':aria-expanded="uitgeklapt"' in html, "de groepkop meldt zijn stand niet"
    assert 'x-data="{ uitgeklapt: true }"' in html, "de groep hoort standaard open"


def test_geen_inline_paneel_meer(client, db_session):
    """Herzien op de feedbackronde van 15 sep (golf 8): het inline openvouwen
    (#510/#676) verdween uit deze lijst — de rij-knop "Bewerken" opent de
    inschrijvingspagina meteen in bewerkmodus. De oude zorg (twee leesweergaven
    van hetzelfde, #648) kan dus niet terugkomen via een paneel dat er niet is.
    """
    activity, comp, _reg = _met_inschrijving(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen").text

    # `x-show="open"` bestaat nu wél — voor de groep-dichtklap; wat weg moet
    # blijven is het rij-paneel met zijn negatie en de disclosure-machinerie.
    assert 'x-show="!open"' not in html, (
        "het inline rij-paneel is terug — ronde 2 haalde het weg")
    assert "detail_disclosure" not in html and "insch-det-" not in html


def test_de_rijknop_heet_details_en_opent_leesmodus(client, db_session):
    """Tweede herroeping (15 sep, later op de dag): de rij-knop heet weer
    "Details" en landt in LEESmodus — dáár staat de consistente
    Bewerken-opener met Verwijderen in het cluster. De `bewerk=1`-sluiproute
    is weg; direct Verwijderen blijft van de rij verdwenen."""
    activity, comp, reg = _met_inschrijving(client, db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen").text

    assert ">Details<" in html
    assert ">Verwijderen<" not in html
    pagina = client.get(f"/admin/inschrijvingen/{reg}?bewerk=1").text
    assert "{ edit: true }" not in pagina, "bewerk=1 hoort geen bewerkmodus meer te openen"
    assert ">Bewerken<" in pagina  # de opener staat op de pagina zelf


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
