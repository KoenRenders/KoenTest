"""De logohoogte is afgeleid van de balkhoogte (#1156).

Koen vroeg tijdens zijn HDEV-ronde hoeveel groter het logo kon zonder de balk
hoger te maken. De ruimte zat in de padding: die nam hoogte die het logo niet
kreeg.

**Wat hier vastligt is de afleiding, niet de opmaak.** Dat de balk op het scherm
even hoog blijft en het logo groter wordt, meet een browser —
`tests_e2e/test_kopbalk_logohoogte.py`, met de gemeten waarden erin. Wat een
servertest wél kan bewaken is dat de ruil één bron heeft: de balkhoogte is de
invariant, de padding is de keuze, en de logohoogte is wat overblijft. Staat die
hoogte als derde getal naast de andere twee, dan loopt ze uit de pas zodra iemand
de padding aanpast — en dat merkt niemand, want de balk blijft dan gewoon staan
terwijl het logo te klein of te groot is.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten): de
`h-[calc(...)]` van het logo terug naar `h-10 md:h-12` → de afleidingstest valt
om op de vaste hoogte; de `{% if site_logo_url %}` rond de padding weggehaald →
de woordmerk-test valt om, want dan krimpt ook die balk mee.
"""
from __future__ import annotations

import re

import pytest

from tests.test_footer_branding import _render

pytestmark = pytest.mark.ui_serverrendered

LOGO = "/api/v1/media/7"
# De hoogte van het logo: de balk min de padding boven en onder. Eén uitdrukking,
# twee variabelen, geen los getal.
LOGOHOOGTE = "h-[calc(var(--balk)_-_2_*_var(--lucht))]"


def _header(html: str) -> str:
    return re.search(r"<header\b.*?</header>", html, re.S).group(0)


def _rij(html: str) -> str:
    """De openingstag van de rij die logo én navigatie draagt."""
    treffer = re.search(r'<div class="max-w-7xl mx-auto px-4[^"]*"', _header(html))
    assert treffer, "de rij van de kopbalk is niet gevonden"
    return treffer.group(0)


def _zonder_commentaar(html: str) -> str:
    """Jinja-commentaar eruit: dat noemt de oude maten met opzet."""
    return re.sub(r"\{#.*?#\}", "", html, flags=re.S)


def test_de_logohoogte_wordt_uit_de_balk_afgeleid():
    kop = _header(_render(site_logo_url=LOGO))

    assert LOGOHOOGTE in kop, (
        f"het logo heeft geen afgeleide hoogte; dan is de ruil een los getal: {kop[:400]}")
    for oud in ("h-10 md:h-12", "py-4 flex"):
        assert oud not in _zonder_commentaar(kop), f"{oud} staat er nog naast de variabele"


def test_de_balk_en_de_lucht_staan_elk_op_een_plaats():
    """De twee maten worden één keer gezet en verder alleen gelezen.

    Gemeten in de browser vóór de wijziging: 80 px breed en 76 px op een
    telefoon. Die getallen zijn de invariant van dit issue, dus ze horen op de
    rij te staan en nergens anders.
    """
    bron = _zonder_commentaar(_render(site_logo_url=LOGO))

    for maat, waarde in (("--balk", "76px"), ("--lucht", "8px")):
        assert bron.count(f"[{maat}:{waarde}]") == 1, maat
    assert bron.count("md:[--balk:80px]") == 1, "de brede variant van de balk"

    rij = _rij(_render(site_logo_url=LOGO))
    assert "py-[var(--lucht)]" in rij, "de padding leest haar maat niet"


def test_zonder_logo_houdt_de_rij_haar_padding():
    """De woordmerk-tak valt buiten dit issue.

    Ze hangt aan dezelfde rij, en ze is een andere hoogte — gemeten 71 px breed
    tegen 80 px met logo. Krimpt de padding daar mee, dan verschuift een balk
    waarover niemand iets gevraagd heeft.
    """
    rij = _rij(_render(site_logo_url=None))

    assert "py-4" in rij, "de woordmerk-tak heeft haar padding niet meer"
    assert "--lucht" not in rij, "de ruil geldt ook zonder logo"
    assert "--balk" not in rij, "de balkhoogte wordt vastgezet zonder logo"


def test_het_aanraakvlak_van_de_menuknop_hangt_niet_aan_de_padding():
    """#804: 44 px is de ondergrens voor een vinger.

    De knop staat in dezelfde rij als het logo. Haar maat moet dus los staan van
    de padding die hier net kleiner wordt — anders krimpt het aanraakvlak mee.
    """
    kop = _header(_render(site_logo_url=LOGO))

    knop = re.search(r"<button[^>]*aria-label[^>]*>", kop)
    assert knop, "de menuknop is niet gevonden"
    assert "min-w-11" in knop.group(0) and "min-h-11" in knop.group(0), (
        "de menuknop draagt haar 44px-aanraakvlak niet meer")
    assert "--lucht" not in knop.group(0), (
        "het aanraakvlak hangt aan de padding en krimpt dus mee")
