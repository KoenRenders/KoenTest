"""#773 — een fix in de JavaScript moet de bezoeker ook echt bereiken.

`app.css` droeg sinds #481 een inhoudshash in zijn URL; de JavaScript werd kaal
geladen en de server stuurde er geen `Cache-Control` bij, alleen een `ETag` en een
`Last-Modified`. Zonder expliciete instructie gokt de browser zelf hoe lang hij het
bestand vers vindt.

Dat is één keer duur geweest. De fix uit #751 stond een uur op HDEV terwijl de
browser nog de `stt.js` van de dag ervóór draaide: de melding stond weer in de
placeholder, de tekst miste de stap die #751 toevoegde, en het microfoon-icoon werd
leeg omdat de oude code `btn.textContent` gebruikte — leeg voor een knop met een SVG
erin. Drie symptomen van een bug die al gerepareerd was. Eén harde herlading loste
alle drie op.

**De tegenproef is de helft die telt.** Dat de URL een `?v=` draagt, zou een
tijdstempel ook halen — en die zou bij elke deploy de cache van elke bezoeker
weggooien, ook voor bestanden die niemand heeft aangeraakt. Daarom staat hieronder
niet alleen "wijzigt mee met de inhoud", maar ook "wijzigt NIET mee met de
wijzigingsdatum".

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `statisch_hash`
vervangen door `str(int(pad.stat().st_mtime))` → de aanraaktest valt om; de
`Cache-Control` uit `_StatischeBestanden` gehaald → beide headertests vallen om.
"""
from pathlib import Path

import pytest

from app.ui import _STATIC_DIR, statisch, statisch_hash

pytestmark = pytest.mark.ui_serverrendered


def test_de_versie_volgt_de_inhoud(tmp_path: Path):
    """Wijzigt de inhoud, dan wijzigt de versie."""
    bestand = tmp_path / "iets.js"
    bestand.write_bytes(b"console.log(1);")
    eerst = statisch_hash(bestand)

    bestand.write_bytes(b"console.log(2);")
    assert statisch_hash(bestand) != eerst, (
        "een gewijzigd bestand houdt dezelfde versie — de browser haalt het nooit op")


def test_de_versie_volgt_de_wijzigingsdatum_niet(tmp_path: Path):
    """Aanraken zonder te wijzigen mag de versie NIET veranderen.

    Dit is de test die een tijdstempel-implementatie afkeurt. Zonder haar zou
    `?v=<mtime>` even groen staan, en dan gooit elke deploy de cache van elke
    bezoeker weg voor bestanden die niet gewijzigd zijn.
    """
    bestand = tmp_path / "iets.js"
    bestand.write_bytes(b"console.log(1);")
    eerst = statisch_hash(bestand)

    import os
    st = bestand.stat()
    os.utime(bestand, (st.st_atime + 86400, st.st_mtime + 86400))

    assert statisch_hash(bestand) == eerst, (
        "de versie hangt aan de wijzigingsdatum en niet aan de inhoud")


def test_een_ontbrekend_bestand_laat_de_pagina_renderen():
    """Een template mag niet omvallen omdat een asset ontbreekt — dan is het scherm
    weg in plaats van een bestand."""
    assert statisch_hash(_STATIC_DIR / "bestaat-niet.js") == "0"


def test_de_helper_levert_het_adres_met_de_hash_van_dat_bestand():
    """En twee verschillende bestanden krijgen twee verschillende versies — anders
    deelt de cache-sleutel zich en bereikt een fix in het ene het andere niet."""
    for naam in ("app.css", "stt.js", "stt-pcm-worklet.js", "vendor/htmx.min.js"):
        assert statisch(naam) == f"/static/{naam}?v={statisch_hash(_STATIC_DIR / naam)}"

    assert statisch("stt.js") != statisch("tts.js")


def test_een_geversioneerd_adres_mag_lang_in_de_cache(client):
    """Het adres wijzigt bij elke wijziging van het bestand, dus lang bewaren is
    veilig — en het is precies wat een inhoudshash je oplevert."""
    r = client.get("/static/app.css", params={"v": "abcd1234"})

    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_een_adres_zonder_versie_mag_dat_niet(client):
    """Zonder versie is een oud bestand niet van een nieuw te onderscheiden. Vijf
    minuten, niet een jaar — en zeker niet 'de browser mag gokken'."""
    r = client.get("/static/app.css")

    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "public, max-age=300"
