"""Het schema is één bron (CR-17 fase 1, snede 1, #1671; C6 tests 2 en de
HTML-helft van 19).

De poort is bewezen met overtredingen tijdens de bouw (genoteerd in de
docstrings): een `schema_for("web")`-aanroep weigerde als onbekende set, een
document met het blok "slider" weigerde met zijn naam, en een attribuut
buiten het schema met "node.attribuut".
"""

import re

import pytest

from app.domains.cms import schema
from app.domains.cms.api import list_pages, render_cms_content, render_document

SEED_SLUGS = ("home-intro", "site-footer")


def _normalise(html):
    return re.sub(r">\s+<", "><", html.strip())


def test_schema_for_noemt_precies_de_page_set():
    """De set `page` in fase 1: tabel en figuur in het invoegmenu, géén
    waardeblok (fase 5), de drie kopniveaus, en de marks van vandaag."""
    config = schema.schema_for("page")
    assert config["insert"] == ["table", "figure"]
    assert [h["level"] for h in config["headings"]] == [1, 2, 3]
    assert set(config["marks"]) == {"bold", "italic", "strike", "link"}
    assert "value" not in config["insert"]
    assert config["nodes"] == sorted(schema.NODES)


def test_het_json_schema_dient_alleen_uit_hetzelfde_schema():
    """Het JSON Schema noemt élke node uit NODES — één bron, twee uitkomsten
    die niet uit elkaar kunnen lopen (C6 2)."""
    import json

    served = json.dumps(schema.json_schema())
    for node in schema.NODES:
        assert f'{{"const": "{node}"}}' in served, f"{node} ontbreekt in het JSON Schema"


def test_een_onbekende_set_is_een_fout():
    """Een setnaam is een identificatie — een onbekende set weigert, en niet
    met een stille lege werkbalk (C6 9's begin)."""
    with pytest.raises(ValueError, match="web"):
        schema.schema_for("web")
    with pytest.raises(ValueError, match="web"):
        schema.validate_document({"type": "doc", "content": []}, "web")


def test_een_onbekend_attribuut_wordt_met_naam_geweigerd():
    """Een attribuut buiten het schema weigert met de naam van node én
    attribuut (bewezen: een `placement="schuin"` weigerde als
    `figure.placement`)."""
    with pytest.raises(ValueError, match="figure.placement"):
        schema.validate_document(
            {
                "type": "doc",
                "content": [
                    {
                        "type": "figure",
                        "attrs": {
                            "media_id": 1,
                            "placement": "schuin",
                            "caption": None,
                            "legacy_size": None,
                        },
                    }
                ],
            }
        )


def test_de_geseede_paginas_renderen_hetzelfde_uit_het_document(db_session):
    """De HTML-helft van C6 19: voor elke geseede pagina is de HTML uit het
    document (dat migratie 198 ervan maakte) gelijk aan de HTML uit `content`
    op de oude weg — witruimte daargelaten. Een pagina die niet verliesvrij
    omzette, houdt haar HTML en heeft geen `published_json`."""
    from app.domains.cms.api import get_translation

    pages = [p for p in list_pages(db_session)]
    assert pages, "geen geseede pagina's gevonden om de migratie te meten"
    gemeten, gelijk, gehouden = 0, 0, 0
    for page in pages:
        gemeten += 1
        translation = get_translation(db_session, page)
        on_page = page.slug not in SEED_SLUGS
        vandaag = _normalise(render_cms_content(page.content or "", db_session, on_page=on_page))
        if translation is None or translation.published_json is None:
            gehouden += 1
            # Het concept bestaat wel (F11) en bevat de woorden.
            assert translation is not None and translation.draft_json is not None
            continue
        uit_document = _normalise(
            render_document(translation.published_json, db_session, on_page=on_page)
        )
        assert uit_document == vandaag, (
            f"pagina {page.slug}: de HTML uit het document wijkt af van vandaag"
        )
        gelijk += 1
    # Minstens één pagina moet de vergelijking echt doorlopen zijn — anders
    # meet deze test niets (de "hij kijkt nergens"-val).
    assert gelijk >= 1, "geen enkele pagina werd als verliesvrij gemeten"
    assert gemeten == gelijk + gehouden
