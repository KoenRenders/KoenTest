"""Beeldverwerking voor de assetbibliotheek.

Bij upload worden afbeeldingen:
- correct geroteerd volgens EXIF-orientatie;
- verkleind tot een redelijke maximale breedte/hoogte (bespaart DB-ruimte);
- voorzien van een aparte, kleine thumbnail voor galerij-grids.

PNG met transparantie (typisch sponsorlogo's) blijft PNG; al de rest wordt naar
JPEG geschreven met nette compressie.
"""
from io import BytesIO
from typing import Optional

from PIL import Image, ImageOps

MAX_FULL = 1600       # langste zijde van het "volledige" beeld
MAX_THUMB = 400       # langste zijde van de thumbnail
JPEG_QUALITY = 82

# Per SOORT en niet per formaat (#1005, CR-10 §3.11). Een A3-affiche vraagt een
# beeld tot 4096 px; 1600 px is daarvoor te weinig. De uitzondering hangt aan de
# soort, zodat een activiteitsfoto er nooit onder valt — een grens die aan het
# formaat hing, zou voor elke grote upload gelden.
#
# Wat NIET verandert: elk beeld wordt heropend en opnieuw gecodeerd. Die
# hercodering is de beveiliging — ze strips EXIF en kleurprofiel, en een bestand
# dat zich als afbeelding voordoet komt er niet doorheen. Alleen de doelmaat
# verschilt.
# `design_render` staat er ook op (#1011): dat is de gerenderde affiche zelf.
# Ze terugbrengen tot 1600 px zou het beeld vernietigen waarvoor 4096 px net is
# toegestaan.
MAX_FULL_BY_KIND = {"design_image": 4096, "design_render": 4096}

# Soorten die verliesvrij blijven (#1011). Een render is een drukklaar beeld van
# een affiche: JPEG zet juist rond letterranden de artefacten neer die je op A3
# ziet staan. Een foto in een affiche (`design_image`) mag wél JPEG worden —
# daar kost verliesvrij alleen bytes.
LOSSLESS_KINDS = frozenset({"design_render"})


ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB per bestand vóór verwerking


class ImageError(ValueError):
    """Onverwerkbare of ongeldige afbeelding."""


def _encode(img: Image.Image, *, keep_alpha: bool) -> tuple[bytes, str]:
    """Hercodeer het beeld — en schrijf géén metadata mee.

    `icc_profile=None` staat er expliciet (#1005). Zonder die parameter haalt
    Pillows PNG-writer het profiel uit `img.info` van het ORIGINEEL en schrijft
    het alsnog weg: gemeten, een profiel van de bron stond gewoon weer in de
    uitvoer. De JPEG-writer leest alleen wat je meegeeft; de parameter staat er
    ook bij, zodat beide takken hetzelfde zeggen.

    EXIF hoeft niet uitgezet te worden: geen van beide writers neemt het uit
    `info` over — nagemeten met een bron die EXIF droeg.

    Dat is geen detail: de hercodering IS de beveiliging van een upload (EXIF
    met locatie eruit, polyglot-bestanden geneutraliseerd), en die belofte staat
    in het contract van dit domein.
    """
    buf = BytesIO()
    if keep_alpha:
        img.save(buf, format="PNG", optimize=True, icc_profile=None)
        return buf.getvalue(), "image/png"
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True,
             icc_profile=None)
    return buf.getvalue(), "image/jpeg"


def _resized(img: Image.Image, max_side: int) -> Image.Image:
    clone = img.copy()
    clone.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return clone


def process_image(raw: bytes, *, kind: str = "") -> dict:
    """Verwerk ruwe bytes tot (full, thumb) + metadata.

    Returns een dict met: data, content_type, thumbnail, thumb_content_type,
    width, height, byte_size.
    Werpt :class:`ImageError` als de input geen geldige afbeelding is.

    `kind` bepaalt de doelmaat (`MAX_FULL_BY_KIND`, #1005) en of de uitvoer
    verliesvrij blijft (`LOSSLESS_KINDS`, #1011); de hercodering zelf gebeurt
    voor élke soort. Het type komt uit de INHOUD —
    Pillow leest de bytes, niet de bestandsnaam.
    """
    if not raw:
        raise ImageError("Leeg bestand")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageError("Bestand te groot")

    try:
        img: Image.Image = Image.open(BytesIO(raw))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ImageError("Geen geldige afbeelding") from exc

    img = ImageOps.exif_transpose(img)
    keep_alpha = kind in LOSSLESS_KINDS or img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )
    if keep_alpha and img.mode != "RGBA":
        img = img.convert("RGBA")

    full = _resized(img, MAX_FULL_BY_KIND.get(kind, MAX_FULL))
    thumb = _resized(img, MAX_THUMB)

    data, content_type = _encode(full, keep_alpha=keep_alpha)
    thumb_data, thumb_content_type = _encode(thumb, keep_alpha=keep_alpha)

    return {
        "data": data,
        "content_type": content_type,
        "thumbnail": thumb_data,
        "thumb_content_type": thumb_content_type,
        "width": full.width,
        "height": full.height,
        "byte_size": len(data),
    }
