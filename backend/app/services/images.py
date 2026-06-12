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
    buf = BytesIO()
    if keep_alpha:
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "image/png"
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return buf.getvalue(), "image/jpeg"


def _resized(img: Image.Image, max_side: int) -> Image.Image:
    clone = img.copy()
    clone.thumbnail((max_side, max_side), Image.LANCZOS)
    return clone


def process_image(raw: bytes) -> dict:
    """Verwerk ruwe bytes tot (full, thumb) + metadata.

    Returns een dict met: data, content_type, thumbnail, thumb_content_type,
    width, height, byte_size.
    Werpt :class:`ImageError` als de input geen geldige afbeelding is.
    """
    if not raw:
        raise ImageError("Leeg bestand")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageError("Bestand te groot")

    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ImageError("Geen geldige afbeelding") from exc

    img = ImageOps.exif_transpose(img)
    keep_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )
    if keep_alpha and img.mode != "RGBA":
        img = img.convert("RGBA")

    full = _resized(img, MAX_FULL)
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
