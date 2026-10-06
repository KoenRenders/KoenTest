"""De verliesvrije migratie van een pagina's HTML naar een document (CR-17 fase
1, #1671; C6 tests 1 en 12).

De eerlijkheid van "verliesvrij" is een meting: `render_document(parse_html(
inhoud))` moet gelijk zijn aan wat de pagina vandaag laat zien (`render_cms_content`
met `on_page=True`), op witruimte na. Deze tests leggen dat vast voor de vormen
die de Trix-pagina's vandaag dragen — en voor de vormen die níet omzetten, met
het milde concept van F11 als gevolg.

Elke test hier kan rood worden: haal de kop-verschuiving of de del-spelling uit
de renderer en de vergelijkingen vallen om.
"""

import pytest

from app.domains.cms.parse import parse_html
from app.domains.cms.render import render_cms_content, render_document
from app.domains.cms.schema import validate_document


def _vandaag(html):
    """Wat de pagina vandaag laat zien: het oude publieke pad, exact zoals
    `ui.py` het aanroept."""
    return render_cms_content(html, None, on_page=True)


def _normalise(html):
    import re

    return re.sub(r">\s+<", "><", html.strip())


@pytest.mark.parametrize(
    "inhoud",
    [
        # Een gewone alinea.
        "<p>Welkom bij de vereniging.</p>",
        # Koppen: opgeslagen als h1–h3, op de pagina een niveau naar beneden
        # (#1656) — het document slaat de keuze van de auteur op (C4.2).
        "<h1>Kop</h1><h2>Subkop</h2><h3>Kleine kop</h3><p>Tekst</p>",
        # Lijsten, inclusief geneste inhoud per item.
        "<ul><li>Eén</li><li>Twee</li></ul><ol><li>Eerst</li><li>Daarna</li></ol>",
        # Marks: vet, cursief, doorgehaald (Trix spelt doorstrepen als <del>),
        # en een link.
        "<p><strong>vet</strong> <em>cursief</em> <del>doorgehaald</del> "
        '<a href="https://example.test">een link</a></p>',
        # Een regeleinde binnen een alinea (Trix' harde break).
        "<p>Regel één<br>Regel twee</p>",
        # Een tabel met kopregel, zoals een redacteur ze via de HTML-deur typte.
        "<table><thead><tr><th>Wat</th><th>Prijs</th></tr></thead>"
        "<tbody><tr><td>Koffie</td><td>€1,00</td></tr></tbody></table>",
        # Een afbeelding uit de bibliotheek, zoals Trix ze opslaat: een
        # attachment-figuur met alt en maat in de JSON (#1173, #1207) — de
        # JSON ge-entiteerd zoals de editor ze wegschrijft.
        '<figure data-trix-attachment="{&quot;contentType&quot;:&quot;image/png&quot;,'
        "&quot;url&quot;:&quot;/api/v1/media/12&quot;,&quot;width&quot;:800,"
        "&quot;height&quot;:600,&quot;alt&quot;:&quot;Het lokaal&quot;,"
        '&quot;size&quot;:&quot;half&quot;}"><img src="/api/v1/media/12" '
        'width="800" height="600"></figure>',
        # Een code blijft TEKST in het document; de renderer vervangt hem
        # zoals vandaag (het waardeblok is fase 5, herziene opdracht #1671).
        "<p>Het lidgeld bedraagt {{membership_price_full}} vanaf {{half_price_start}}.</p>",
        # Een formulierknop (#1567) blijft werken: de code blijft tekst, de
        # rendering zet de knop eromheen.
        "<p>{{form:berichten|Schrijf ons}}</p>",
    ],
)
def test_de_migratie_is_eerlijk(inhoud):
    """render(parse(html)) is wat de pagina vandaag laat zien (C6 12)."""
    document = parse_html(inhoud, on_page=True)
    assert document is not None, f"pagina zet niet om: {inhoud!r}"
    validate_document(document)
    assert _normalise(render_document(document, None, on_page=True)) == _normalise(_vandaag(inhoud))


def test_de_tabel_overleeft_een_bewerking():
    """C6 1: een tabel bewaard, herladen, één cel gewijzigd, opnieuw bewaard —
    de documenten verschillen in exact die cel."""
    document = parse_html(
        "<table><thead><tr><th>Wat</th></tr></thead>"
        "<tbody><tr><td>Koffie</td></tr><tr><td>Thee</td></tr></tbody></table>"
    )
    table = document["content"][0]
    rij = table["content"][1]["content"][0]
    cel = rij["content"][0]["content"][0]
    assert cel["text"] == "Koffie"
    cel["text"] = "Koffie met melk"
    assert render_document(document, None) == (
        "<table><thead><tr><th>Wat</th></tr></thead>"
        "<tbody><tr><td>Koffie met melk</td></tr><tr><td>Thee</td></tr></tbody></table>"
    )


def test_een_pagina_die_niet_zuiver_omzet_houdt_haar_html():
    """Een citaat staat niet in het schema (C4.2): de pagina zet niet verliesvrij
    om — strict geeft None, en de site blijft haar HTML tonen (F11)."""
    document = parse_html("<blockquote>Een citaat van iemand.</blockquote>", on_page=True)
    assert document is None


def test_het_milde_concept_bewaart_de_woorden():
    """F11: de milde parse levert een concept met de woorden, geen None — de
    redacteur vergelijkt en publiceert zelf."""
    document = parse_html(
        "<blockquote>Een citaat van iemand.</blockquote><p>En een alinea.</p>",
        on_page=True,
        lenient=True,
    )
    assert document is not None
    validate_document(document)
    words = render_document(document, None, target="text")
    assert "citaat van iemand" in words
    assert "En een alinea." in words


def test_een_code_blijft_tekst_en_wordt_toch_vervangen():
    """Het document bewaart de code als tekst (fase 5 maakt het blok); de
    renderer vervangt hem met de actuele waarde, zoals vandaag."""
    document = parse_html("<p>Het lidgeld: {{membership_price_full}}</p>", on_page=True)
    teksten = [node["text"] for node in document["content"][0]["content"] if node["type"] == "text"]
    assert any("{{membership_price_full}}" in t for t in teksten), "de code is geen tekst"
    html = render_document(document, None, on_page=True)
    assert "{{membership_price_full}}" not in html
    assert "€" in html


def test_het_fragment_zonder_kopverschuiving():
    """Het home-intro-blok rendert zónder `on_page`: de kop blijft op zijn eigen
    niveau — het document slaat de keuze op, de plek kiest de tag (C4.2)."""
    document = parse_html("<h1>Kop</h1>", on_page=False)
    assert render_document(document, None) == "<h1>Kop</h1>"
    document = parse_html("<h1>Kop</h1>", on_page=True)
    assert render_document(document, None, on_page=True) == "<h2>Kop</h2>"


def test_de_tekstlezer_geeft_woorden():
    """De tekstweergave van een document (snede 1, voor de chatbot): geen
    tags, de code zijn waarde in woorden, de figuur zijn alt-tekst."""
    document = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": "Kop"}],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Het lidgeld: {{membership_price_full}}"},
                ],
            },
            {
                "type": "figure",
                "attrs": {
                    "media_id": 3,
                    "alt": "Het lokaal",
                    "placement": "full",
                    "caption": None,
                    "legacy_size": None,
                },
            },
        ],
    }
    text = render_document(document, None, target="text")
    assert "<" not in text
    assert "Kop" in text
    assert "Het lokaal" in text
    assert "€" in text
    assert "{{" not in text
