"""Actieve-link-markering in de publieke navigatie (#608, ui-conventies §B2.10).

De balk markeerde niet waar je stond: alle links zagen er identiek uit. Nu is
zachtblauw inactief en wit+onderlijn de pagina waar je bent, met `aria-current`
voor de schermlezer — kleur alleen is geen markering (design-system §5).

We toetsen op het gerenderde antwoord van echte routes, niet op de template-tekst:
de invariant die telt is dat er per pagina precies één item oplicht, en dat het
juiste item oplicht ook wanneer de href niet gelijk is aan het pad (/archief).
"""
import re

import pytest

# <a href="…" … aria-current="page">Label</a> — het label van elk gemarkeerd item.
ACTIEF = re.compile(r'<a href="([^"]+)"[^>]*aria-current="page"[^>]*>([^<]*)</a>')


def _actieve_hrefs(html: str) -> list[str]:
    return [m.group(1) for m in ACTIEF.finditer(html)]


@pytest.mark.parametrize("pad,verwacht", [
    ("/", "/"),
    ("/fotos", "/fotos"),
    ("/activiteiten/archief", "/archief"),
])
def test_de_juiste_nav_link_is_gemarkeerd(client, pad, verwacht):
    html = client.get(pad).text
    hrefs = set(_actieve_hrefs(html))
    assert hrefs == {verwacht}, f"op {pad} verwacht {verwacht}, kreeg {hrefs}"


def test_archief_markeert_ondanks_de_redirect():
    """/archief is een 302 naar /activiteiten/archief (#405-e). Zonder het
    `match`-argument zou de Archief-link daar nooit oplichten."""
    inhoud = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "app" / "ui" / "templates" / "site_base.html"
    ).read_text()
    assert 'match="/activiteiten/archief"' in inhoud


def test_home_licht_niet_op_elders(client):
    """Zonder exact=True zou "/" op élk pad matchen — alles begint met een slash."""
    assert "/" not in _actieve_hrefs(client.get("/fotos").text)


def test_inactieve_links_dragen_de_zachte_tint(client):
    """Zachtblauw = inactief. De token (blue-100 = #d2e3f6), niet de hex uit de mock."""
    html = client.get("/").text
    assert 'href="/fotos" class="hover:underline text-blue-100"' in html


def test_desktop_en_mobiel_krijgen_dezelfde_markering(client):
    """Beide lijsten lopen via één macro; twee treffers per gemarkeerd item."""
    html = client.get("/fotos").text
    assert len(_actieve_hrefs(html)) == 2
