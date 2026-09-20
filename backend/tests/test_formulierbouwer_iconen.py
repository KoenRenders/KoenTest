"""#698 — prullenbak en potlood in plaats van × en ⚙, met tooltips.

Koen vroeg of `×` voor verwijderen en `⚙` voor bewerken zo in het design-systeem
staan. Dat doen ze niet: §1.5 schrijft één Lucide-set voor via `ui.icon()`, en die
glyphs stonden er niet als keuze maar omdat de set geen prullenbak en geen potlood
had.

**Het harde argument is geen smaak.** `×` betekende in deze app al *sluiten* — de
toast sluit met precies datzelfde teken. Eén glyph, twee betekenissen: de ene
handeling is gratis, de andere vernietigt een optie met haar `skip_to_section` en
haar id. Het tandwiel betekent *instellingen*, en dát staat op ditzelfde scherm
bovenaan als een echte knop die iets anders doet.

**De valkuil waar test 2 voor bestaat:** `ui.icon()` faalt **stil** bij een
onbekende naam — een lege, onzichtbare SVG. Een typefout geeft dus een knop zonder
icoon en geen enkele foutmelding. Daarom toetsen deze tests het gerenderde
`<path>`, niet de macro-aanroep.
"""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_agnostisch

# Een herkenbaar stuk van het officiële Lucide-pad, niet het hele pad: een test die
# op de laatste decimaal let, breekt bij elke Lucide-update zonder dat er iets mis is.
PRULLENBAK = 'd="M3 6h18"'
POTLOOD = 'd="m15 5 4 4"'


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _bouwer(client, admin_headers) -> str:
    r = client.post("/api/v1/forms", json={
        "title": "Iconen", "status": "draft",
        "fields": [{"field_type": "radio", "label": "Kies", "position": 0,
                    "options": [{"label": "Een", "position": 0},
                                {"label": "Twee", "position": 1}]}],
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    _login(client)
    return client.get(f"/admin/formulieren/{r.json()['id']}").text


# ── 1. De iconen staan er, en de glyphs niet meer ──────────────────────────

def test_de_prullenbak_staat_klaar_in_de_set():
    """Sinds #1090 rendert de bouwer de prullenbak nergens meer: het verwijderen
    van een optie is een tekstknop in de actiebalk geworden, net als dat van een
    veld en een sectie. Het icoon blijft in de set, zoals het potlood hieronder —
    de eerstvolgende symboolknop "verwijderen" hoort hém te nemen en geen ×.

    Tot #1090 toetste dit het gerenderde `<path>` in de bouwer, omdat `ui.icon()`
    bij een onbekende naam stil een lege SVG geeft; nu er geen aanroep meer is,
    is het geregistreerde pad het enige wat te toetsen valt.
    """
    macros = open("app/ui/templates/_macros.html", encoding="utf-8").read()
    assert '"trash-2"' in macros
    assert PRULLENBAK in macros, "het geregistreerde pad klopt niet meer"


def test_het_potlood_staat_klaar_in_de_set():
    """Het potlood is vandaag nérgens in gebruik, en dat is geen vergissing.

    Het kwam er met #698 voor de ⚙-knop op de optierij, en #699 haalde die knop
    weg: de velden staan nu inline, dus er valt niets meer te openen. Elke andere
    bewerkactie in de app is een knop mét tekst ("Bewerken"), en die hoort geen
    icoon te dragen.

    Het blijft geregistreerd omdat het de vastgelegde woordenschat is — potlood =
    bewerken — zodat de volgende symbolische bewerkknop niet opnieuw een glyph
    verzint. Deze test toetst dus de definitie en niet een render; een test die
    beweert dat het ergens gebruikt wordt, zou liegen.
    """
    macros = open("app/ui/templates/_macros.html", encoding="utf-8").read()
    assert '"pencil"' in macros
    assert POTLOOD in macros, "het geregistreerde pad klopt niet meer"


def _optie_verwijderknop(html: str, tot: str = "</button>") -> str:
    """De verwijderknop van de eerste optie — sinds #1090 een tekstknop uit
    `ui.action_bar`, herkenbaar aan haar route."""
    import re

    treffer = re.search(r'hx-post="/admin/formulieren/\d+/opties/\d+/verwijderen"', html)
    assert treffer, "geen optie-verwijderknop gevonden"
    start = treffer.start()
    return html[html.rindex("<button", 0, start):html.index(tot, start)]


def test_de_glyphs_zijn_weg_van_de_knoppen(client, admin_headers):
    html = _bouwer(client, admin_headers)
    assert "⚙" not in html, "het tandwiel staat er nog"
    # `×` mag nog voorkomen als sluitknop van de toast-sjabloon in de schil; wat weg
    # moet is de verwijderknop. Sinds #1090 is dat een tekstknop ("Verwijderen")
    # uit de actiebalk: geen teken en geen icoon meer, de tekst draagt de betekenis.
    knop = _optie_verwijderknop(html)
    assert "×" not in knop, f"de verwijderknop draagt nog een ×: {knop[:200]}"
    assert "Verwijderen" in knop


def test_verwijderen_blijft_rood(client, admin_headers):
    """§2.12: een verwijderknop is altijd rood. De tekst vervangt het teken, niet
    het signaal."""
    html = _bouwer(client, admin_headers)
    knop = _optie_verwijderknop(html, tot=">")
    assert "red" in knop, knop


# ── 2. De tooltip ──────────────────────────────────────────────────────────

# "Optie bewerken" stond hier tot #699; die knop bestaat niet meer — de velden van
# een optie staan nu altijd inline, dus er valt niets te openen. "Veld verwijderen"
# verdween in golf 6 (#913) en "Optie verwijderen" in #1090, om dezelfde reden:
# het verwijderen zit in de actiebalk als tekstknop, en een knop met tekst krijgt
# geen tooltip. Wat rest aan symboolknoppen zijn de verplaatspijlen (`ui.reorder`).
@pytest.mark.parametrize("label", ["Naar boven", "Naar onder"])
def test_elke_symboolknop_draagt_een_tooltip(client, admin_headers, label):
    """De schermlezer had het label al; wie met een muis werkt zag enkel een
    symbool."""
    html = _bouwer(client, admin_headers)
    start = html.index(f'aria-label="{label}"')
    knop = html[html.rindex("<button", 0, start):html.index(">", start)]
    assert f'title="{label}"' in knop, knop


def test_een_knop_met_tekst_krijgt_geen_tooltip(client, admin_headers):
    """De keerzijde: zonder deze grens zou élke knop een tooltip krijgen die
    herhaalt wat er al leesbaar op staat."""
    html = _bouwer(client, admin_headers)
    start = html.index(">Opslaan<")
    knop = html[html.rindex("<button", 0, start):start]
    assert "title=" not in knop, knop


# ── 3. De sluitknoppen elders blijven ──────────────────────────────────────

def test_de_toast_sluit_nog_altijd_met_een_kruisje(client, admin_headers):
    """Dat is de toets of de regel klopt: ná deze wijziging betekent `×` in de hele
    app nog maar één ding. Verdwijnt hij hier óók, dan is de regel te breed
    toegepast en heeft "sluiten" geen teken meer."""
    _login(client)
    html = client.get("/admin/formulieren").text
    start = html.index('id="htmx-foutmelding"')
    assert "&times;" in html[start:start + 800], (
        "de sluitknop van de foutmelding is meeverdwenen")


# ── 4. De sectiebalk verwijdert ook met een prullenbak (#706) ───────────────

def test_de_sectiebalk_verwijdert_niet_meer_met_een_kruisje(client, admin_headers):
    """`section_bar` schreef zijn knop als rauwe HTML binnen een kit-macro, en die
    vorm glipte door de gate van #698 — die kijkt naar macro-aanroepen.

    Op de bouwer stond daardoor nog steeds hetzelfde teken voor "sluit deze melding"
    en voor "vernietig deze sectie met haar velden, opties en sprongregels".
    """
    r = client.post("/api/v1/forms", json={
        "title": "Sectiebalk", "status": "draft",
        "sections": [{"title": "Een", "position": 0}],
        "fields": [{"field_type": "text", "label": "V", "position": 0,
                    "section_index": 0}],
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    _login(client)
    html = client.get(f"/admin/formulieren/{r.json()['id']}").text

    # Golf 6 (#913, A2): de sectiebalk draagt geen verwijderknop meer — het
    # sectie-verwijderen is een tekstknop in de actiebalk van de sectievorm.
    # De oorspronkelijke zorg (× voor vernietigen) kan dus niet terugkomen via
    # deze balk; het kale aria-label was er het kenmerk van.
    assert 'aria-label="Verwijderen"' not in html, \
        "de sectiebalk heeft weer een eigen (symbool)verwijderknop"
    # De verhuisde knop bestaat écht: rood en met tekst, in de sectievorm.
    assert html.count(">Verwijderen<") >= 2, \
        "sectie- en formulier-verwijderen horen als tekstknop in een actiebalk"


def test_de_foutmelding_sluit_nog_steeds_met_een_kruisje(client, admin_headers):
    """Na #698 én #706 betekent `×` in de hele app nog precies één ding — en dat
    ding heeft nog steeds een knop. Zonder deze test zou "haal de kruisjes weg" ook
    slagen."""
    _login(client)
    html = client.get("/admin/formulieren").text
    start = html.index('id="htmx-foutmelding"')
    assert "&times;" in html[start:start + 800]
