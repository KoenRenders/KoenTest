"""#749 — de drietrap sectietitel → vraag → optie op een publiek formulier.

De vraag werd gerenderd met `ui.label()`, en die is gebouwd voor een beheerformulier:
een grijs labeltje boven een omkaderd invoerveld, waar het véld de inhoud is. Op een
enquête is die verhouding omgekeerd, en dan valt de vraag weg. Gemeten in een echte
browser, vóór en na:

| | vóór | na |
|---|---|---|
| sectietitel | 16px / 700 | 18px / 700 |
| vraag | 14px / 500, **#374151** | 16px / 600, **#14171c** |
| optie | 14px / 400, #14171c | ongewijzigd |

De vraag stond dus in middengrijs terwijl haar eigen antwoorden bijna zwart zijn —
kleurcontrast weegt zwaarder dan gewicht, dus het halfvette `font-medium` haalde dat
niet terug.

**Deze test legt de klassen vast, niet het uiterlijk.** Het optische oordeel is
gemaakt door voor en na naast elkaar te renderen (zoals bij #744); wat een test kan
bewaken is dat een latere opruiming de drietrap niet platslaat door overal dezelfde
stijl te zetten.

De harde regressie die hier kon ontstaan — de foutmarkering uit #741 die het
vraagblok zoekt via `[data-veld]` — staat in
`tests_e2e/test_formulier_wizard_stap.py` en is groen gebleven.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `ui.vraag` terug
op `ui.label` in formulier.html → de eerste test valt om op de vraagstijl; de
`space-y-6` terug op `space-y-4` → de ritmetest valt om.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_serverrendered

MACROS = (Path(__file__).resolve().parents[1] / "app/ui/templates/_macros.html").read_text()
FORMULIER = (Path(__file__).resolve().parents[1]
             / "app/domains/forms/templates/formulier.html").read_text()


def test_de_drie_niveaus_zijn_onderscheiden():
    """Sectietitel, vraag en optie verschillen in grootte én gewicht."""
    vraagstijl = MACROS[MACROS.index("{% macro vraag("):]
    vraagstijl = vraagstijl[:vraagstijl.index("{%- endmacro %}")]
    assert "text-base" in vraagstijl and "font-semibold" in vraagstijl
    assert "text-ink" in vraagstijl, (
        "de vraag hoort in volle inktkleur; in grijs staat ze onder haar eigen "
        "antwoorden")

    assert "ui.vraag(f.label" in FORMULIER, "het formulier gebruikt de vraagstijl niet"
    assert '<h2 class="text-lg font-bold' in FORMULIER, (
        "de sectietitel staat niet één stap boven de vraag")


def test_de_labelstijl_blijft_wat_ze_was():
    """`ui.label()` aanpassen zou élk beheerscherm verschuiven (#749).

    Deze test is de rem op de voor de hand liggende 'opruiming': de twee stijlen
    samenvoegen. Ze bestaan naast elkaar omdat ze twee verschillende verhoudingen
    dienen.
    """
    labelstijl = MACROS[MACROS.index("{% macro label("):]
    labelstijl = labelstijl[:labelstijl.index("{%- endmacro %}")]
    assert "text-sm font-medium text-gray-700" in labelstijl


def test_het_ritme_zet_de_ruimte_boven_de_vraag():
    """Nabijheid doet het werk: ruim tussen de vragen, dicht bij de opties.

    Zonder dit las de lijst als één massa, ook mét grotere letters — alles stond op
    gelijke afstand.
    """
    assert "space-y-6" in FORMULIER, "de vragen staan niet verder uit elkaar"
    assert "space-y-1" in FORMULIER, "de opties staan niet dicht bij hun vraag"


def test_de_markering_verschuift_de_vraag_niet():
    """#741 zette `border-l-4 … pl-3` erbij op het moment van markeren, en dat
    verschóóf de vraag precies wanneer je hem staat te lezen. De rand staat er nu
    altijd, doorzichtig; alleen de kleur wisselt."""
    assert 'class="border-l-4 border-transparent pl-3"' in FORMULIER
    assert "'border-l-4', 'border-red-600', 'pl-3'" not in FORMULIER, (
        "de markering voegt de rand nog steeds toe in plaats van hem te kleuren")
