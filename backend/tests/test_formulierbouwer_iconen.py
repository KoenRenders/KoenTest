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

def test_de_prullenbak_wordt_echt_gerenderd(client, admin_headers):
    """Toetst het `<path>`, niet de macro-aanroep.

    `ui.icon()` geeft bij een onbekende naam een lege SVG zonder te klagen, dus
    `lead_icon="trash-1"` zou een knop zonder icoon opleveren en elke test op de
    aanroep zou groen blijven.
    """
    html = _bouwer(client, admin_headers)
    assert PRULLENBAK in html, "de prullenbak rendert niet (typefout in de naam?)"


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


def test_de_glyphs_zijn_weg_van_de_knoppen(client, admin_headers):
    html = _bouwer(client, admin_headers)
    assert "⚙" not in html, "het tandwiel staat er nog"
    # `×` mag nog voorkomen als sluitknop van de toast-sjabloon in de schil; wat weg
    # moet is de verwijderknop. Die herken je aan zijn aria-label.
    start = html.index('aria-label="Optie verwijderen"')
    knop = html[html.rindex("<button", 0, start):html.index("</button>", start)]
    assert "×" not in knop, f"de verwijderknop draagt nog een ×: {knop[:200]}"
    assert PRULLENBAK in knop


def test_verwijderen_blijft_rood(client, admin_headers):
    """§2.12: een verwijderknop is altijd rood. Het icoon vervangt het teken, niet
    het signaal."""
    html = _bouwer(client, admin_headers)
    start = html.index('aria-label="Optie verwijderen"')
    knop = html[html.rindex("<button", 0, start):html.index(">", start)]
    assert "red" in knop, knop


# ── 2. De tooltip ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", ["Optie verwijderen", "Optie bewerken",
                                   "Veld verwijderen"])
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
