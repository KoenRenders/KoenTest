"""#702 — de verplaatsknoppen lazen als een spinner.

Twee 14px-chevrons, grijs, zonder rand of achtergrond, verticaal gestapeld zonder
tussenruimte: letterlijk de vorm van een spinner op een getalveld. Koen las het als
een scrollbalk of een sleepgreep.

Drie oorzaken tegelijk, en ze versterken elkaar:

- **chevron in plaats van pijl** — een chevron betekent uitklappen of scrollen, een
  pijl betekent verplaatsen. Waarschijnlijk de grootste van de drie;
- **geen chroom en geen gat** — twee knoppen versmelten dan tot één strookje;
- **`text-gray-400`** — dat leest als versiering, niet als bediening.

**De goede versie stond al in de codebase**, in `section_bar`. Er waren dus twee
verplaatsvormen, terwijl de docstring van `reorder` zei: *"Dé enige reorder-vorm;
schermen bouwen geen eigen pijltjesknoppen meer."* Die zin was onwaar. `section_bar`
gebruikt nu `reorder`, en daarmee klopt ze weer — dat is de tweede test hieronder, en
de reden dat de twee niet opnieuw uit elkaar kunnen lopen.
"""
import re

import pytest

from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_agnostisch

MACROS = "app/ui/templates/_macros.html"
# Herkenbare stukken van de officiële Lucide-paden.
PIJL_OMHOOG = 'd="m5 12 7-7 7 7"'
PIJL_OMLAAG = 'd="M12 5v14"'


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _bouwer(client, admin_headers) -> str:
    r = client.post("/api/v1/forms", json={
        "title": "Reorder", "status": "draft",
        "sections": [{"title": "Een", "position": 0},
                     {"title": "Twee", "position": 1}],
        "fields": [{"field_type": "radio", "label": "Kies", "position": 0,
                    "section_index": 0,
                    "options": [{"label": "A", "position": 0},
                                {"label": "B", "position": 1},
                                {"label": "C", "position": 2}]}],
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    _login(client)
    return client.get(f"/admin/formulieren/{r.json()['id']}").text


def _knoppen(html: str, label: str) -> list[str]:
    """Elke <button> met dit aria-label, als losse string."""
    uit = []
    for m in re.finditer(f'aria-label="{label}"', html):
        start = html.rindex("<button", 0, m.start())
        uit.append(html[start:html.index(">", m.start())])
    return uit


# ── 1. De vorm ─────────────────────────────────────────────────────────────

def test_de_knoppen_dragen_pijlen_en_geen_chevrons(client, admin_headers):
    """Toetst het gerenderde `<path>`: `ui.icon` faalt stil bij een onbekende naam,
    dus `arrow-upp` zou een knop zonder icoon geven en geen foutmelding."""
    html = _bouwer(client, admin_headers)
    assert PIJL_OMHOOG in html, "de pijl omhoog rendert niet"
    assert PIJL_OMLAAG in html, "de pijl omlaag rendert niet"


def test_de_knoppen_hebben_chroom_en_staan_naast_elkaar(client, admin_headers):
    html = _bouwer(client, admin_headers)
    knop = _knoppen(html, "Naar boven")[0]
    assert "rounded" in knop and "px-1.5" in knop, (
        f"geen chroom, dus twee knoppen versmelten tot één strookje: {knop}")

    macros = open(MACROS, encoding="utf-8").read()
    blok = macros[macros.index("{% macro reorder("):macros.index("{%- endmacro %}",
                                                                macros.index("{% macro reorder("))]
    assert "inline-flex items-center" in blok, "de knoppen staan nog gestapeld"
    assert "flex-col" not in blok, "verticaal gestapeld — dat was juist de spinnervorm"
    assert "gap-" in blok, "geen tussenruimte tussen de twee knoppen"


def test_de_knoppen_lezen_niet_meer_als_versiering(client, admin_headers):
    """`text-gray-400` was de derde oorzaak."""
    knop = _knoppen(_bouwer(client, admin_headers), "Naar boven")[0]
    assert "text-gray-400" not in knop, knop


# ── 2. Eén vorm, en dat blijft zo ──────────────────────────────────────────

def test_section_bar_gebruikt_dezelfde_macro():
    """De docstring van `reorder` claimt "dé enige reorder-vorm". Die zin was onwaar
    zolang `section_bar` zijn eigen pijltjes bouwde; deze test houdt haar waar."""
    macros = open(MACROS, encoding="utf-8").read()
    blok = macros[macros.index("{% macro section_bar("):]
    blok = blok[:blok.index("{%- endmacro %}")]
    assert "reorder(" in blok, "section_bar bouwt weer eigen pijltjesknoppen"
    assert "icon('arrow-up'" not in blok, blok


def test_er_is_maar_een_plek_met_pijltjesknoppen():
    """Breder dan section_bar: geen enkel sjabloon hoort zelf `arrow-up` naast
    `arrow-down` te zetten. Zo ontstond dit gat."""
    from pathlib import Path

    fouten = []
    for pad in (Path(MACROS).resolve().parents[3] / "app").rglob("*.html"):
        tekst = pad.read_text(encoding="utf-8")
        if "arrow-up" in tekst and "arrow-down" in tekst and pad.name != "_macros.html":
            fouten.append(str(pad))
    assert not fouten, f"eigen pijltjesknoppen buiten de kit: {fouten}"


# ── 3. Wat bij het herbouwen kon sneuvelen ─────────────────────────────────

def test_de_eindstanden_blijven_uitgeschakeld(client, admin_headers):
    """Bestond al en moet blijven: de bovenste omhoog en de onderste omlaag."""
    html = _bouwer(client, admin_headers)
    omhoog = _knoppen(html, "Naar boven")
    omlaag = _knoppen(html, "Naar onder")

    assert any("disabled" in k for k in omhoog), "geen enkele ↑ is uitgeschakeld"
    assert any("disabled" in k for k in omlaag), "geen enkele ↓ is uitgeschakeld"
    assert any("disabled" not in k for k in omhoog), (
        "álle ↑ staan uit — dan werkt verplaatsen nergens")


def test_de_aria_labels_blijven(client, admin_headers):
    html = _bouwer(client, admin_headers)
    assert _knoppen(html, "Naar boven"), "aria-label 'Naar boven' is verdwenen"
    assert _knoppen(html, "Naar onder"), "aria-label 'Naar onder' is verdwenen"


def test_de_knoppen_dragen_ook_een_tooltip(client, admin_headers):
    """Symboolknoppen (§2.12, #698). Ze gaan niet door de `button`-macro, dus de
    tooltip staat hier met de hand — en dat is precies waarom hij getoetst wordt."""
    knop = _knoppen(_bouwer(client, admin_headers), "Naar boven")[0]
    assert 'title="Naar boven"' in knop, knop
