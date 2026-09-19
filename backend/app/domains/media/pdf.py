"""A PDF gets a picture of its first page (#1019).

Why: the newsletter block of CR-05 (#984) shows an image next to the text, and
for an activity that still has to happen the poster is the only source — photos
come from the album and that exists only afterwards. Posters arrive here as PDF
more often than not, and no mail client shows a PDF.

The same move as the SVG logo (#989): keep the original, store a raster
rendering next to it, and let the surfaces that cannot show the original use
that one. The rendering lives in the asset's existing ``thumbnail`` column.

Rendered with **pypdfium2** (PDFium, the renderer in Chrome; Apache/BSD). It
ships as a wheel with the library inside, so the image needs no apt package —
and its licence, unlike PyMuPDF's AGPL, fits a public repository.

A PDF is a document and a document can be hostile. Three limits, each cheap:
the file size is already capped at upload, only the FIRST page is touched, and
a failure to parse or render returns ``None`` instead of raising — an affiche
without a picture is a letter without a picture, not a broken upload.
"""
from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

# Imported at module level on purpose: `check_imports.py` imports every module,
# so a missing package breaks the build instead of the first poster upload.
import pypdfium2
from PIL import Image

logger = logging.getLogger(__name__)

PDF_CONTENT_TYPE = "application/pdf"
PNG_CONTENT_TYPE = "image/png"

#: Longest side of the rendering. An A4 poster at 800 px is ~565 px wide, twice
#: what the newsletter block shows on a sharp screen, and a few tens of KB.
MAX_SIDE = 800


def first_page_png(raw: bytes) -> Optional[bytes]:
    """The first page of ``raw`` as PNG bytes, or None when that cannot be done.

    None is a valid outcome: an encrypted PDF, a file that is not a PDF at all,
    or a renderer that refuses. The caller keeps the document as it is.
    """
    if not raw:
        return None
    document = None
    try:
        document = pypdfium2.PdfDocument(raw)
        if len(document) < 1:
            return None
        page = document[0]
        width, height = page.get_width(), page.get_height()
        longest = max(width or 0, height or 0)
        if longest <= 0:
            return None
        image = page.render(scale=MAX_SIDE / longest).to_pil()
        if image.mode != "RGB":
            image = image.convert("RGB")
        out = BytesIO()
        image.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception as exc:  # noqa: BLE001 — a poster without a picture is not an error
        logger.info("PDF-affiche niet gerenderd: %s", exc)
        return None
    finally:
        if document is not None:
            try:
                document.close()
            except Exception:  # noqa: BLE001
                pass
