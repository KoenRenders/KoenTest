"""Een sponsorlogo wordt niet meer als JPEG bewaard (#1131).

Gemeld door Koen op 21 september 2026: rond de dunne lijnen van het MONA-logo op
zijn Bowlen-affiche stond een rij verticale streepjes boven de letters, met een
gele ertussen, en een blauw tikje onder "veilig".

**De oorzaak zat in media, niet in de Design Studio.** Elke upload werd
hercodeerd naar JPEG op kwaliteit 82, behalve voor de soorten in
`LOSSLESS_KINDS`. Een sponsorlogo komt meestal al als JPEG van de sponsor
binnen, dus dat was een **tweede** compressie op lijnwerk — precies het
materiaal waar JPEG het slechtst mee omgaat. Gemeten op het echte logo, zonder
herschaling: 147 KB → 26 KB, kleurafwijkingen tot 82 van 255, en 549 punten die
wit horen te zijn en dat niet meer waren.

**Wat deze tests vastleggen, en waarom de tweede de belangrijkste is.** Dat een
logo er verliesvrij uitkomt, is de reparatie. Dat een *activiteitsfoto* nog
steeds hercodeerd wordt, is de reden dat het een uitzondering blijft: foto's
horen gecomprimeerd te worden, en een fix die stilletjes álles verliesvrij maakt
laat elk fotoalbum in de databank opzwellen. Zonder die tweede test zou
"zet `keep_alpha` altijd aan" hier even groen staan.

De hercodering zélf blijft voor élke soort bestaan — dat is de beveiliging van
een upload (EXIF en kleurprofiel eruit, een polyglot-bestand geneutraliseerd),
niet de compressie. De laatste test bewaakt dat voor de nieuwe soorten.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
`sponsor` uit `LOSSLESS_KINDS` gehaald → de eerste twee vallen om (volledig
beeld én miniatuur); `keep_alpha` altijd waar gemaakt → de foto-test valt om
met `image/png` en afwijking nul.
"""
from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.domains.media.images import LOSSLESS_KINDS, process_image

pytestmark = pytest.mark.ui_agnostisch

BREEDTE, HOOGTE = 751, 261   # de maat van Koens logo; onder MAX_FULL, dus geen herschaling


def _lijnwerk() -> bytes:
    """Een logo-achtig beeld: dunne donkere lijnen op wit, plus wat tekst.

    Als JPEG opgeslagen, want zo komt een sponsorlogo binnen — en dat is precies
    het geval dat een tweede compressie zichtbaar beschadigt.
    """
    img = Image.new("RGB", (BREEDTE, HOOGTE), (255, 255, 255))
    tekenaar = ImageDraw.Draw(img)
    for x in range(0, BREEDTE, 9):
        tekenaar.line([(x, 20), (x, 240)], fill=(20, 20, 20), width=1)
    tekenaar.text((30, 120), "MONA veilig", fill=(10, 60, 150))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _kanaalafwijking(bron: bytes, uit: bytes) -> int:
    """De grootste afwijking per kleurkanaal tussen bron en resultaat."""
    a = Image.open(BytesIO(bron)).convert("RGB")
    b = Image.open(BytesIO(uit)).convert("RGB")
    assert a.size == b.size, (a.size, b.size)
    return max(abs(p - q) for pa, pb in zip(a.getdata(), b.getdata())
               for p, q in zip(pa, pb))


# ── 1. Het logo komt er verliesvrij uit ──────────────────────────────────────

@pytest.mark.parametrize("soort", ["sponsor", "tenant_logo"])
def test_een_logo_wordt_niet_opnieuw_gecomprimeerd(soort):
    """Hetzelfde materiaal, dezelfde plek: een logo op een affiche en in de
    kopbalk van elke publieke pagina."""
    bron = _lijnwerk()

    uit = process_image(bron, kind=soort)

    assert uit["content_type"] == "image/png", "een logo hoort niet als JPEG terug"
    assert _kanaalafwijking(bron, uit["data"]) == 0, (
        "het logo is opnieuw gecomprimeerd: de pixels wijken af van wat er "
        "opgeladen werd (#1131)")
    assert (uit["width"], uit["height"]) == (BREEDTE, HOOGTE), "er is toch herschaald"


def test_de_miniatuur_volgt_dezelfde_weg(soort="sponsor"):
    """Anders staat er in een galerijraster alsnog een JPEG van hetzelfde logo."""
    uit = process_image(_lijnwerk(), kind=soort)

    assert uit["thumb_content_type"] == uit["content_type"] == "image/png"


# ── 2. En een foto blijft wél gecomprimeerd ──────────────────────────────────

def test_een_activiteitsfoto_wordt_nog_altijd_hercodeerd():
    """De test die bewijst dat de uitzondering een uitzondering blijft.

    Een foto hoort gecomprimeerd te worden: verliesvrij kost hier alleen bytes,
    en een album loopt in de honderden beelden. Gemeten op ruis — het slechtste
    geval voor PNG — is 189 KB als JPEG 115 KB en als PNG 642 KB.
    """
    bron = _lijnwerk()

    uit = process_image(bron, kind="activity_photo")

    assert uit["content_type"] == "image/jpeg", (
        "een activiteitsfoto hoort JPEG te blijven — anders is elke upload "
        "verliesvrij geworden")
    assert uit["thumb_content_type"] == "image/jpeg"
    assert _kanaalafwijking(bron, uit["data"]) > 0, (
        "de foto is niet hercodeerd; dan is de compressie stilzwijgend "
        "uitgeschakeld voor alles")


def test_de_uitzonderingslijst_blijft_een_uitzondering():
    """Vier soorten, en geen van de twee foto-soorten erbij.

    Een lijst die groeit tot ze alles bevat, is geen uitzondering meer. Deze
    assert is de rem: wie er een soort bij zet, leest hier waarom dat een
    afweging is.
    """
    assert LOSSLESS_KINDS == {"design_render", "sponsor", "tenant_logo"}, LOSSLESS_KINDS
    assert "activity_photo" not in LOSSLESS_KINDS
    assert "design_image" not in LOSSLESS_KINDS, (
        "een foto ín een affiche mag wél JPEG worden (#1011)")


# ── 3. De hercodering blijft de beveiliging ──────────────────────────────────

@pytest.mark.parametrize("soort", ["sponsor", "tenant_logo"])
def test_een_logo_wordt_nog_steeds_heropend_en_ontdaan_van_metadata(soort):
    """Verliesvrij betekent niet "de bytes ongemoeid doorgeven".

    De hercodering IS de beveiliging van een upload: EXIF met locatie eruit, een
    kleurprofiel eruit, en een bestand dat zich alleen als afbeelding voordoet
    komt er niet doorheen. Die belofte mag een verliesvrije soort niet omzeilen.
    """
    img = Image.new("RGB", (60, 40), (200, 30, 30))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95,
             exif=b"Exif\x00\x00II*\x00\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00",
             icc_profile=b"ICC-PROFIEL-VAN-DE-BRON")
    bron = buf.getvalue()

    uit = process_image(bron, kind=soort)

    assert uit["data"] != bron, "de bytes zijn ongewijzigd doorgegeven"
    terug = Image.open(BytesIO(uit["data"]))
    assert not terug.info.get("icc_profile"), "het kleurprofiel van de bron staat er nog"
    assert b"Exif" not in uit["data"], "EXIF uit de bron staat er nog"


def test_een_bestand_dat_alleen_een_afbeelding_lijkt_wordt_geweigerd():
    """Ook voor een verliesvrije soort: de weigering zit in het heropenen."""
    from app.domains.media.images import ImageError

    with pytest.raises(ImageError):
        process_image(b"GIF89a dit is geen echte afbeelding", kind="sponsor")
