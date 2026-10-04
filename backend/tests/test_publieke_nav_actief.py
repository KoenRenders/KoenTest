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

pytestmark = pytest.mark.ui_serverrendered

# <a href="…" … aria-current="page">Label</a> — het label van elk gemarkeerd item.
ACTIEF = re.compile(r'<a href="([^"]+)"[^>]*aria-current="page"[^>]*>([^<]*)</a>')


def _actieve_hrefs(html: str) -> list[str]:
    return [m.group(1) for m in ACTIEF.finditer(html)]


@pytest.mark.parametrize(
    "pad,verwacht",
    [
        ("/", "/"),
        ("/fotos", "/fotos"),
        ("/activiteiten/archief", "/archief"),
    ],
)
def test_de_juiste_nav_link_is_gemarkeerd(client, pad, verwacht):
    html = client.get(pad).text
    hrefs = set(_actieve_hrefs(html))
    assert hrefs == {verwacht}, f"op {pad} verwacht {verwacht}, kreeg {hrefs}"


def test_archief_markeert_ondanks_de_redirect():
    """/archief is een 302 naar /activiteiten/archief (#405-e). Zonder het
    `match`-argument zou de Archief-link daar nooit oplichten.

    Since #1476 the header's module links come from the registry, and the
    `match` travels with the Archief item of `public_nav` instead of standing
    in the template. The rendered behaviour is the parametrized case above.
    """
    from app.kernel.modules import ModuleCode, current_modules
    from app.ui import _public_nav

    token = current_modules.set(frozenset(code.value for code in ModuleCode))
    try:
        archief = [n for n in _public_nav("public_items") if n["href"] == "/archief"]
    finally:
        current_modules.reset(token)
    assert archief and archief[0]["match"] == "/activiteiten/archief", archief


def test_home_licht_niet_op_elders(client):
    """Zonder exact=True zou "/" op élk pad matchen — alles begint met een slash."""
    assert "/" not in _actieve_hrefs(client.get("/fotos").text)


def test_inactieve_links_dragen_de_zachte_tint(client):
    """An inactive link is white at 90 % on the band, the active one full white,
    semibold and underlined — #1588 replaced the soft blue (`text-blue-100`) by it.
    """
    html = client.get("/").text
    nav = html[html.index('<nav id="site-nav-breed"') :]
    nav = nav[: nav.index("</nav>")]
    fotos = re.search(r'<a href="/fotos" class="([^"]*)"([^>]*)>', nav)
    assert fotos, "the Foto's link is not in the header's row"
    assert "text-white/90" in fotos.group(1).split()
    assert "underline" not in fotos.group(1).split() and "aria-current" not in fotos.group(2)
    home = re.search(r'<a href="/" class="([^"]*)" aria-current="page">', nav)
    assert home, "the active link is not marked"
    assert {"text-white", "font-semibold", "underline", "decoration-2"} <= set(
        home.group(1).split()
    )
    assert "text-white/90" not in home.group(1).split()
    assert "text-blue-100" not in html


def test_desktop_en_mobiel_krijgen_dezelfde_markering(client):
    """Beide lijsten lopen via één macro; twee treffers per gemarkeerd item."""
    html = client.get("/fotos").text
    assert len(_actieve_hrefs(html)) == 2
