"""#1522 — the meeting PDF embeds its fonts as TrueType, each with a ToUnicode.

A board member's Android phone, in the built-in preview opened from WhatsApp,
showed every text line of a meeting PDF as scattered wrong glyphs; the logo and
the layout were right. pdfium (the engine of Android's own PdfRenderer) did not
reproduce it: it rendered and extracted the text correctly. What the PDF did
carry was the least supported font form: every font embedded as CFF in an
OpenType wrapper (`CIDFontType0`, `FontFile3/OpenType`). The `.ttf` files were
CFF fonts under another name (repackaged from Debian's OTF, #939), and the two
italics were `.otf`.

Since #1522 the fonts are the official Inter 4.1 TrueType files (glyf outlines),
subset as before, and WeasyPrint embeds them as `CIDFontType2` with `FontFile2`,
the form every PDF reader handles. These tests hold that, and that the text a
reader extracts is the source text, for regular, bold and italic runs.

Proven red against master `f0323657`: the PDF test fails on `/CIDFontType0`
with `/FontFile3`, and the file test on six CFF files.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

import pytest

from app.domains.meetings.api import (
    SectionKind,
    add_item,
    create_meeting,
    sections_of,
    update_item,
)

pytestmark = pytest.mark.ui_agnostisch

APP = Path(__file__).resolve().parents[3]
TEMPLATE = APP / "domains" / "meetings" / "templates" / "meeting_pdf.html"
FONTS = APP / "static"

NOTES = (
    "<p>Gewone tekst, <strong>vette tekst</strong>, <em>schuine tekst</em> en "
    "<strong><em>vet en schuin</em></strong>.</p>"
)
SOURCE = "Gewone tekst, vette tekst, schuine tekst en vet en schuin."


def _fonts(pdf: bytes) -> dict[str, dict]:
    """Per embedded font: its CID subtype, its font file key, its ToUnicode."""
    from pypdf import PdfReader

    found: dict[str, dict] = {}
    for page in PdfReader(io.BytesIO(pdf)).pages:
        for ref in ((page.get("/Resources") or {}).get("/Font") or {}).values():
            font = ref.get_object()
            descendant = font["/DescendantFonts"][0].get_object()
            descriptor = descendant["/FontDescriptor"].get_object()
            found[str(font["/BaseFont"])] = {
                "cid": str(descendant["/Subtype"]),
                "file": next(
                    k for k in ("/FontFile", "/FontFile2", "/FontFile3") if k in descriptor
                ),
                "to_unicode": "/ToUnicode" in font,
            }
    return found


def test_every_font_of_a_meeting_pdf_is_truetype_with_a_to_unicode(db_session):
    import pypdfium2 as pdfium

    from app.domains.meetings import pdf as meeting_pdf
    from app.domains.meetings.admin_ui import _pdf_context

    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    misc = next(s for s in sections_of(db_session, meeting) if s.kind is SectionKind.MISC)
    item = add_item(db_session, meeting, misc, title="Vrij punt met opmaak")
    update_item(db_session, meeting, item.id, notes=NOTES)

    pdf = meeting_pdf.render(context=_pdf_context(db_session, meeting, kind="report"))

    fonts = _fonts(pdf)
    names = " ".join(fonts)
    assert {"Inter", "Inter-Bold", "Inter-Italic", "Inter-Bold-Italic"} <= {
        n.split("+", 1)[1] for n in fonts
    }, f"the runs of the test did not reach their fonts: {names}"
    wrong = {
        n: f
        for n, f in fonts.items()
        if f != {"cid": "/CIDFontType2", "file": "/FontFile2", "to_unicode": True}
    }
    assert not wrong, f"not TrueType with a ToUnicode: {wrong}"

    text = pdfium.PdfDocument(pdf)[0].get_textpage().get_text_range()
    assert SOURCE in " ".join(text.split()), "the text a reader extracts is the source text"


def test_every_font_the_pdf_names_is_a_truetype_file():
    """The template's own fonts: a CFF file (`.otf`, or a `.ttf` that holds CFF)
    would be embedded as FontFile3 again."""
    from fontTools.ttLib import TTFont

    sources = re.findall(r'src:\s*url\("([^"]+)"\)', TEMPLATE.read_text(encoding="utf-8"))
    assert len(sources) >= 6, f"only {len(sources)} @font-face sources — did the template change?"
    not_truetype = [s for s in sources if "glyf" not in TTFont(FONTS / s, lazy=True)]
    assert not not_truetype, f"not TrueType (no glyf table): {not_truetype}"
