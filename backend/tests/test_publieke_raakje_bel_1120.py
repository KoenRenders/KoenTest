"""De publieke pagina is weg; de bel eronder werkt door (#1120).

Besloten door Koen op 21 september 2026: *"de publieke /raakje mag weg, die
gebruikt niemand."* Gemeten in Umami op PROD: sinds 15 juni 2026 3451
gebeurtenissen en **nul** op een pad met `raakje` erin (de homepage 2276,
`/fotos` 114). Te verklaren, want niets in de toepassing verwees ernaar — geen
navigatielink, geen voetlink, geen knop. Ze was alleen bereikbaar door het adres
te typen.

**De val bij het opruimen, en waarom deze test bestaat.** De pagina en de
zwevende bel delen één eindpunt: `POST /raakje/vraag`. Haal je dat mee weg met
`GET /raakje`, dan valt Raakje op de **hele publieke site** stil — en dat zie je
niet aan de pagina die je weghaalt.

Daarom toetst dit bestand het eindpunt **via de bel** en niet door de route bij
naam aan te roepen: de bestemming komt uit de gerenderde bel zelf, zoals htmx ze
leest. Roept een test de route rechtstreeks aan, dan blijft hij groen terwijl de
bel naar iets anders wijst — precies het gat dat deze samenhang verbergt.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
`POST /raakje/vraag` uit `chatbot/ui.py` gehaald → de beltest valt om met 405 op
de bestemming die de bel zelf noemt; `GET /raakje` teruggezet → de 404-test.
"""
from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def chat_aan(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")


def _bel(html: str) -> str:
    """Het paneel van de zwevende bel, uit een gerenderde publieke pagina."""
    start = html.find('id="raakje-widget-gesprek"')
    assert start != -1, "de zwevende bel staat niet op deze pagina"
    return html[start:]


def test_de_pagina_geeft_404(client, chat_aan):
    """Geen omleiding: er linkt niets naar dat adres en er komt geen verkeer op.
    Komt er ooit toch iets bovendrijven, dan is een omleiding één regel."""
    assert client.get("/raakje").status_code == 404


def test_de_bel_staat_op_een_publieke_pagina(client, db_session, chat_aan):
    html = client.get("/").text
    paneel = _bel(html)
    assert "Typ je vraag…" in paneel
    assert 'data-stt-target="#raakje-widget-vraag"' in paneel, "geen microfoon"
    assert "data-tts-toggle" in html, "geen voorleesknop"


def test_het_eindpunt_van_de_bel_beantwoordt_een_vraag(client, db_session, chat_aan):
    """Via de bel: de bestemming komt uit haar eigen formulier, niet uit deze test."""
    html = client.get("/").text
    bestemming = re.search(r'<form[^>]*hx-post="([^"]+)"[^>]*>', _bel(html))
    assert bestemming, "de bel heeft geen formulier met een bestemming"
    doel = bestemming.group(1)
    assert doel == "/raakje/vraag", f"de bel post naar {doel!r}"

    antwoord = client.post(doel, data={"vraag": "Wat is Raak?"})
    assert antwoord.status_code == 200, antwoord.text[:200]
    assert "Wat is Raak?" in antwoord.text, "de vraag komt niet terug in het gesprek"
    assert "data-raakje-answer" in antwoord.text, "er kwam geen antwoordballon"


def test_niets_verwijst_nog_naar_de_verdwenen_pagina(client):
    """Een dood adres in een sjabloon is een link die op een 404 uitkomt.

    Op de sjablonen en niet op één gerenderde pagina: een link die alleen op een
    zelden bezocht scherm staat, zou anders door de mazen glippen.
    """
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app"
    fouten = []
    for sjabloon in app.rglob("templates/*.html"):
        for nr, regel in enumerate(sjabloon.read_text().splitlines(), 1):
            if re.search(r'href="/raakje"|hx-get="/raakje"', regel):
                fouten.append(f"{sjabloon.relative_to(app)}:{nr}")
    assert not fouten, (
        "deze sjablonen wijzen nog naar de verdwenen pagina /raakje:\n  "
        + "\n  ".join(fouten))
