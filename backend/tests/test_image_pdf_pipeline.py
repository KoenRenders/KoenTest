"""Regressie-net voor de pillow- en pypdf-upgrades (#267): oefent de echte
API-paden die de app gebruikt, zodat een major-bump die ze breekt meteen rood
wordt i.p.v. stil te falen.

- pillow: JPEG-decode/-encode, RGBA/alpha, en de LANCZOS-resize in process_image.
- pypdf: PdfReader / .pages / .extract_text — rechtstreeks getest, want de
  wrapper _extract_pdf_text_layer slikt excepties (een breuk zou anders als ""
  verdwijnen).
"""
from io import BytesIO

from PIL import Image

from app.domains.media.images import process_image


def test_process_image_jpeg():
    buf = BytesIO()
    Image.new("RGB", (80, 80), (200, 30, 30)).save(buf, "JPEG")
    out = process_image(buf.getvalue())
    assert out["content_type"] == "image/jpeg"
    assert out["width"] == 80 and out["height"] == 80
    assert out["data"] and out["thumbnail"]


def test_process_image_rgba_keeps_alpha():
    buf = BytesIO()
    Image.new("RGBA", (80, 80), (255, 0, 0, 128)).save(buf, "PNG")
    out = process_image(buf.getvalue())
    # Transparantie blijft PNG (sponsorlogo's e.d.).
    assert out["content_type"] == "image/png"
    assert out["thumb_content_type"] == "image/png"


def test_process_image_resizes_large_image():
    buf = BytesIO()
    Image.new("RGB", (3000, 1000), (10, 10, 10)).save(buf, "PNG")
    out = process_image(buf.getvalue())
    # LANCZOS-resize tot max 1600 langste zijde.
    assert out["width"] <= 1600 and out["height"] <= 1600


def test_pypdf_reader_api_still_works():
    """De pypdf-API die de app gebruikt (PdfReader, .pages, .extract_text) blijft
    werken na de bump. Een geldige (image-)PDF via Pillow als input."""
    from pypdf import PdfReader

    buf = BytesIO()
    Image.new("RGB", (120, 120), "white").save(buf, "PDF")
    reader = PdfReader(BytesIO(buf.getvalue()))
    assert len(reader.pages) == 1
    assert isinstance(reader.pages[0].extract_text(), str)


def test_extract_pdf_text_layer_on_image_pdf_returns_empty():
    from app.domains.media.api import _extract_pdf_text_layer

    buf = BytesIO()
    Image.new("RGB", (120, 120), "white").save(buf, "PDF")
    assert _extract_pdf_text_layer(buf.getvalue()) == ""
