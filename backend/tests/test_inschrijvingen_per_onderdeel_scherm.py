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
        "contact_name": "An Janssens", "contact_email": "an@example.com",
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


def test_de_rij_wijkt_voor_het_paneel(client, db_session):
    """De kern: één weergave, niet twee onder elkaar."""
    activity, comp, _reg = _met_inschrijving(client, db_session)
    _login(client)
    html = client.get(
        f"/admin/activiteiten/{activity.id}/onderdelen/{comp.id}/inschrijvingen").text

    assert 'x-show="!open"' in html, (
        "de rij blijft staan naast het paneel — twee leesweergaven van hetzelfde")
    assert 'x-show="open"' in html


def test_er_staat_een_uitweg_uit_het_paneel(client, db_session):
    activity, comp, _reg = _met_inschrijving(client, db_session)
    _login(client)
    html = client.get(
        f"/admin/activiteiten/{activity.id}/onderdelen/{comp.id}/inschrijvingen").text
    assert "Sluiten" in html, "het paneel is niet te sluiten"


def test_de_rijknop_heet_geen_bewerken(client, db_session):
    """Twee knoppen met dezelfde naam die iets anders doen — de rijknop vouwt een
    detail open, de knop ín het paneel schakelt de bewerkstand om."""
    activity, comp, _reg = _met_inschrijving(client, db_session)
    _login(client)
    html = client.get(
        f"/admin/activiteiten/{activity.id}/onderdelen/{comp.id}/inschrijvingen").text

    assert "Details" in html
    assert html.count(">Bewerken<") == 0, (
        "de rij biedt nog een knop 'Bewerken' aan naast die in het paneel")


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

    assert paneel.count('x-show="!edit">Bewerken<') == 1
    # Leesregel én invulveld: precies één van elk.
    assert paneel.count('value="An Janssens"') == 1
    assert "An Janssens" in paneel
