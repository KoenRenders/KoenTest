"""Een pagina-afbeelding krijgt een maat (#1207).

Koen na het invoegen van zijn eerste pagina-afbeelding: *"Ik voegde er één in en
het was meteen een zeer groot geval."* Het gedrag klopte — `.cms-content img`
begrenst een beeld op de kolombreedte — maar er was geen manier om te zeggen dat
het kleiner mocht.

**Drie vaste maten en geen vrij percentage**, beslist door Koen: met een vrij
getal staan er op termijn pagina's met 37 %, 40 % en 45 % naast elkaar die er
rommelig uitzien zonder dat iemand ziet waarom.

**De maat reist in de bijlage-gegevens en niet als klasse op de `<img>`**, om
exact dezelfde gemeten reden als de alt van #1173: de editor maakt van élke
`<img>` een bijlage en houdt alleen bron, breedte en hoogte over. Een klasse op
de tag zou dus stil verdwijnen bij de tweede bewaring. Dit bestand toetst de
serverhelft; dat de editor de maat werkelijk in die JSON zet en dat ze een
rondgang overleeft, staat in `tests_e2e/test_page_image_size_1207.py`.

**De vertaling van maat naar klasse is een whitelist, en dat is de
beveiligingshelft.** De waarde komt uit admin-geschreven JSON en belandt in een
`class`-attribuut, dat de sanitisatie-allowlist op élke tag toelaat. Door hem
door `IMAGE_SIZES` te halen levert een onbekende waarde géén klasse op in plaats
van wat er ook maar getypt was.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
- `IMAGE_SIZES` vervangen door een doorgeeflus (`klasse = data.get("size")`) →
  de whitelist-test valt om met `class="stiekem"` in de uitvoer;
- de `size`-tak uit `_attributes_onto_image` gehaald → de drie maat-tests vallen
  om, en de alt-test blijft groen — precies zoals het hoort, want die twee zijn
  onafhankelijk.
"""

from __future__ import annotations

import pytest

from app.domains.cms.render import IMAGE_SIZES, image_attributes_from_attachment, render_cms_content

pytestmark = pytest.mark.ui_agnostisch

ALT = "Schermafdruk van het aanmeldformulier"


def _figuur(*, maat: str | None = None, alt: str = ALT, mid: int = 7) -> str:
    """De vorm die de editor bewaart: dubbele aanhalingstekens, `&quot;` erin.

    Letterlijk zoals gemeten in een headless Chromium bij #1173. Met enkele
    aanhalingstekens grijpt de regex niet — dat is bij het meten van dit issue
    één keer misgegaan en het kostte een meting die niets zei.
    """
    velden = [
        f"&quot;alt&quot;:&quot;{alt}&quot;",
        "&quot;contentType&quot;:&quot;image&quot;",
        f"&quot;url&quot;:&quot;/api/v1/media/{mid}&quot;",
    ]
    if maat is not None:
        velden.insert(1, f"&quot;size&quot;:&quot;{maat}&quot;")
    return (
        f'<div><figure data-trix-attachment="{{{",".join(velden)}}}" '
        f'data-trix-content-type="image" class="attachment attachment--preview">'
        f'<img src="/api/v1/media/{mid}">'
        f'<figcaption class="attachment__caption"></figcaption></figure></div>'
    )


# ── 1. De drie maten ────────────────────────────────────────────────────────


@pytest.mark.parametrize("maat,klasse", [("klein", "cms-beeld-klein"), ("half", "cms-beeld-half")])
def test_de_maat_wordt_een_klasse_op_de_img(maat, klasse):
    html = render_cms_content(_figuur(maat=maat))

    assert f'class="{klasse}"' in html, f"maat {maat!r} levert geen klasse op de <img>:\n{html}"
    assert "<img" in html and "data-trix-attachment" not in html


def test_volle_breedte_draagt_geen_klasse():
    """De standaard is het gedrag van vóór dit issue, en dat hoort ongewijzigd
    te renderen — anders zou elke bestaande pagina een klasse erbij krijgen."""
    html = render_cms_content(_figuur(maat="vol"))

    assert "cms-beeld-" not in html, f"volle breedte draagt toch een maatklasse:\n{html}"
    assert "<img" in html


def test_een_afbeelding_zonder_maat_rendert_als_voorheen():
    """Alles wat vóór #1207 ingevoegd is, draagt geen `size` in zijn JSON."""
    html = render_cms_content(_figuur())

    assert "cms-beeld-" not in html
    assert f'alt="{ALT}"' in html, "de alt van #1173 sneuvelde op een oude afbeelding"


# ── 2. De whitelist ─────────────────────────────────────────────────────────


def test_een_onbekende_maat_levert_geen_klasse_op():
    """De beveiligingshelft: de waarde komt uit admin-geschreven JSON en zou
    anders ongefilterd in een `class` belanden."""
    html = render_cms_content(_figuur(maat="stiekem"))

    assert "stiekem" not in html, f"een onbekende maat is als klasse doorgegeven:\n{html}"
    assert "cms-beeld-" not in html
    assert "<img" in html, "de afbeelding zelf hoort gewoon te blijven staan"


def test_de_maten_zijn_er_drie_en_vol_is_leeg():
    """De rem, in de vorm van `LOSSLESS_KINDS` in media: wie er een maat bij
    zet, leest hier waarom dat een afweging is — drie maten was de keuze, en een
    vierde maakt pagina's opnieuw onderling ongelijk."""
    assert set(IMAGE_SIZES) == {"klein", "half", "vol"}, IMAGE_SIZES
    assert IMAGE_SIZES["vol"] == "", (
        "volle breedte hoort geen klasse te dragen — dat is de stand van vóór "
        "#1207 en bestaande pagina's moeten ongewijzigd renderen"
    )


# ── 3. De alt van #1173 blijft naast de maat bestaan ────────────────────────


def test_de_alt_en_de_maat_reizen_samen():
    """Beide komen uit dezelfde JSON; een reparatie aan de ene mag de andere
    niet wegnemen. Dat is geen theorie: ze delen één functie."""
    html = render_cms_content(_figuur(maat="half"))

    assert f'alt="{ALT}"' in html, f"de alt is verdwenen naast de maat:\n{html}"
    assert 'class="cms-beeld-half"' in html


def test_een_handmatige_klasse_wint():
    """Wie in het HTML-bronvenster zelf een klasse zet, maakte een keuze — zelfde
    regel als voor een handmatige alt."""
    eigen = _figuur(maat="klein").replace("<img src=", '<img class="eigen" src=')

    html = render_cms_content(eigen)

    assert 'class="eigen"' in html, f"de handmatige klasse is overschreven:\n{html}"
    assert "cms-beeld-klein" not in html


def test_een_bestandsbijlage_krijgt_nog_altijd_geen_maat():
    """De contentType-controle uit #1173 blijft gelden voor beide attributen."""
    pdf = (
        '<div><figure data-trix-attachment="{&quot;size&quot;:&quot;klein&quot;,'
        "&quot;contentType&quot;:&quot;application/pdf&quot;,"
        '&quot;url&quot;:&quot;/api/v1/media/9&quot;}">'
        '<img src="/api/v1/media/9"></figure></div>'
    )

    assert image_attributes_from_attachment(pdf) == pdf
