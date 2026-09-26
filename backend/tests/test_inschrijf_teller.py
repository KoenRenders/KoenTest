"""#1171/#1172: de aantal-teller op het publieke inschrijfformulier.

**#1171 — waarom hij bestaat.** Een `<input type="number">` toont op iOS Safari
nooit op-en-neer-pijltjes, op geen enkele iPhone. Op een telefoon moest je het
veld dus aantikken, de `0` selecteren en een cijfer typen — op het publieke
inschrijfformulier, waar 80% van het bezoek mobiel is. Koen zag het naast een
lid met een oudere iPhone en vermoedde het toestel; het toestel was het niet.

**De val zit in de herberekening.** Het totaal wordt server-side herrekend op
`change`. Een waarde die JavaScript zet stuurt géén `change`, dus een `+` die
dat niet expliciet afvuurt laat het cijfer klimmen terwijl *Totaal: €0,00* blijft
staan — en dan bevestigt iemand een bedrag dat niet op het scherm klopt.

Die keten (klik → waarde → change → htmx → nieuw totaal) loopt door de browser en
wordt daar gemeten: `tests_e2e/test_inschrijf_teller.py`. Wat hier staat is de
markupkant ervan — snel, en precies genoeg om te zien dát de schakel er is.

**#1172** — bij precies één product opent het formulier op 1.
"""
from __future__ import annotations

import re

import pytest

from tests.conftest import seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

MACROS = "app/ui/templates/_macros.html"


def _formulier(client, activity, component) -> str:
    respons = client.get(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}")
    assert respons.status_code == 200
    return respons.text


def _veld(html: str, product_id: int) -> str:
    """Het `<input>` van dit product, uit de gerenderde teller."""
    treffer = re.search(rf'<input[^>]*id="product-{product_id}"[^>]*>', html)
    assert treffer, f"geen aantalveld voor product {product_id} in het formulier"
    return treffer.group(0)


# ── #1171: de teller zelf ───────────────────────────────────────────────────

def test_the_quantity_field_has_its_own_minus_and_plus(client, db_session):
    """Geen browserpijltjes meer nodig: er staan twee echte knoppen.

    Ze dragen allebei een `aria-label` — een − of een + is voor een schermlezer
    geen tekst, en de UI-poort eist dat al voor een knop zonder woorden.
    """
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    html = _formulier(client, activity, component)

    assert 'aria-label="Eén minder' in html and 'aria-label="Eén meer' in html, (
        "de teller mist een knop of een aria-label")
    # Het product staat in het label, zodat twee tellers op één formulier uit
    # elkaar te houden zijn door wie het scherm niet ziet.
    assert product.name in html


def test_the_buttons_fire_a_real_change_event(client, db_session):
    """De belangrijkste schakel, en de makkelijkste om te vergeten.

    Zonder `dispatchEvent(new Event('change'…))` klimt het getal wel maar blijft
    het totaal op €0,00 staan: htmx hangt aan `change`, en een waarde die
    JavaScript zet vuurt die niet af.

    Deze test kijkt naar de markup; de keten tot en met het nieuwe totaal wordt
    in de browser gemeten (`tests_e2e/test_inschrijf_teller.py`). Rood bewezen
    door de regel uit de macro te halen: dan faalt deze, en faalt de e2e op het
    stilstaande totaal.
    """
    activity, component, _p = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    html = _formulier(client, activity, component)

    assert "dispatchEvent(new Event('change'" in html, (
        "de teller vuurt geen change af — het totaal zou op €0,00 blijven staan "
        "terwijl het aantal klimt")


def test_the_htmx_attributes_stay_on_the_input(client, db_session):
    """Eén pad naar de herberekening, niet twee.

    De `hx-*`-attributen horen op het invoerveld en niet op de knoppen: de teller
    vuurt een echte `change` af op dat veld, dus klikken en typen lopen langs
    precies dezelfde weg. Verhuizen ze naar de knoppen, dan bestaat er een tweede
    pad dat bij typen niet meeloopt.
    """
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    html = _formulier(client, activity, component)

    veld = _veld(html, product.id)
    assert "hx-post=" in veld and 'hx-trigger="change, keyup delay:300ms"' in veld

    knoppen = re.findall(r'<button[^>]*aria-label="Eén (?:minder|meer)[^>]*>', html)
    assert len(knoppen) == 2, f"twee knoppen verwacht, gevonden: {len(knoppen)}"
    for knop in knoppen:
        assert "hx-post=" not in knop, (
            "de knop doet zijn eigen htmx-verzoek; dan loopt klikken langs een "
            "ander pad dan typen")


def test_the_field_keeps_its_name_and_its_bounds(client, db_session):
    """Het getal blijft een echt invoerveld, met dezelfde `name` als vroeger.

    De server ziet dus niets anders dan voor #1171, en typen of plakken blijft
    werken. `min` en `max` gelden voor het veld én voor de knoppen — de macro
    leest ze van het veld.
    """
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    product.max_participants = 7
    db_session.commit()

    veld = _veld(_formulier(client, activity, component), product.id)
    assert f'name="product_{product.id}"' in veld
    assert 'min="0"' in veld and 'max="7"' in veld


def test_each_button_is_at_least_44px_by_class(client, db_session):
    """De maatvoering staat in de macro; de browser meet het in de e2e.

    `h-11 w-11` is 2,75rem = 44px (#804). Deze assertie is de goedkope helft —
    ze betrapt iemand die de klasse weghaalt. De echte meting (`getBoundingClientRect`)
    staat in `tests_e2e/test_inschrijf_teller.py`, want een klassenaam is geen maat.
    """
    activity, component, _p = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    html = _formulier(client, activity, component)

    knoppen = re.findall(r'<button[^>]*aria-label="Eén (?:minder|meer)[^>]*>', html)
    assert len(knoppen) == 2
    for knop in knoppen:
        assert "h-11" in knop and "w-11" in knop, (
            f"een tellerknop is kleiner dan 44px: {knop[:120]}")


# ── #1172: waarmee het formulier opent ──────────────────────────────────────

def test_one_product_opens_at_one(client, db_session):
    """Het gewone geval: één product, dus het totaal toont meteen de prijs.

    Tegenproef: de voorvulling losgekoppeld van het aantal producten → dan opent
    ook het geval met twee producten op 1 en valt de test hieronder om.
    """
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    html = _formulier(client, activity, component)

    assert 'value="1"' in _veld(html, product.id)
    # Op het TOTAALBLOK en niet op de hele pagina: de prijs van het product staat
    # ook los in de regel erboven, dus `"10,00" in html` staat groen met een
    # totaal van €0,00. Dat was hij ook — de e2e betrapte het, deze assertie niet.
    totaal = re.search(r'<div id="totaal-\d+">(.*?)</div>', html, re.S)
    assert totaal, "geen totaalblok in het formulier"
    assert "10,00" in totaal.group(1), (
        f"het totaal toont de prijs niet bij het openen: {totaal.group(1).strip()!r}")


def test_two_products_open_at_zero(client, db_session):
    """Met meer dan één product is voorvullen een keuze maken voor de bezoeker.

    Zonder deze test zou een voorvulling die altijd 1 zet ook groen staan.
    """
    from app.domains.activities.api import ActivityProduct

    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    db_session.add(ActivityProduct(component_id=component.id,
                                   name="Tweede product", price=5,
                                   is_free=False))
    db_session.commit()

    html = _formulier(client, activity, component)
    for veld in re.findall(r'<input[^>]*id="product-\d+"[^>]*>', html):
        assert 'value="0"' in veld, f"dit veld opent niet op 0: {veld[:120]}"
    assert product.name in html


def test_a_product_with_maximum_zero_cannot_exist(db_session):
    """#1172 noemde dit als randgeval; het bestaat niet, en dát is het antwoord.

    Het issue vroeg: één product met maximum 0 moet op 0 openen, want 1 zou een
    aantal zijn dat niet mag. Bij het bouwen bleek de databank zo'n rij te
    weigeren — `ck_activity_products_max_participants_positive` (migratie 040)
    eist `max_participants > 0 OR IS NULL`. Het geval kan dus niet ontstaan, en
    een test die het naspeelt zou de rij niet eens bewaard krijgen.

    Deze test legt daarom de ECHTE reden vast in plaats van een onbereikbaar
    scherm. De guard in `_standaard_aantal` blijft staan als vangnet voor een
    migratie die de grens ooit loslaat, maar hij is vandaag geen levend pad —
    dat staat ook in zijn docstring, zodat niemand hem later als bewijs leest
    dat het geval voorkomt.
    """
    from sqlalchemy.exc import IntegrityError

    _a, _c, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False)
    product.max_participants = 0
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_default_quantity_never_exceeds_the_maximum(db_session):
    """Het vangnet zelf, rechtstreeks getoetst.

    Rechtstreeks en niet via het scherm, juist omdat de databank de toestand niet
    toelaat: dit is de enige manier om te zien dát de guard doet wat hij belooft.
    Haal hem uit `_standaard_aantal` en deze test wordt rood.
    """
    from types import SimpleNamespace

    from app.domains.activities.ui import _standaard_aantal

    # Sinds #1191 neemt `_standaard_aantal` de PRODUCTENLIJST en niet het onderdeel:
    # het formulier toont enkel de publiek boekbare producten, en dit aantal hoort bij
    # wat er staat. Wat de guard toetst is ongewijzigd.
    vol = [SimpleNamespace(max_participants=0)]
    ruim = [SimpleNamespace(max_participants=5)]
    onbeperkt = [SimpleNamespace(max_participants=None)]
    twee = [SimpleNamespace(max_participants=5), SimpleNamespace(max_participants=5)]

    assert _standaard_aantal(vol) == 0
    assert _standaard_aantal(ruim) == 1
    assert _standaard_aantal(onbeperkt) == 1
    assert _standaard_aantal(twee) == 0


def test_what_the_visitor_typed_survives_a_validation_error(client, db_session):
    """De voorvulling geldt bij het EERSTE openen en overschrijft niets.

    Een bewuste 0 is het scherpste geval: die is gelijk aan de oude standaard, dus
    een herrendering die stiekem opnieuw voorvult, valt alleen hier op.
    """
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False)

    respons = client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={"contact_name": "", "contact_email": "x", "phone": "",
              f"product_{product.id}": "0"})
    assert respons.status_code == 200
    assert 'value="0"' in _veld(respons.text, product.id), (
        "de herrendering zette het aantal terug op de standaard; wat de bezoeker "
        "invulde hoort te blijven staan")
