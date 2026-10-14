"""The document door checks the content of an uploaded file (#1905).

Every way a document is stored — a poster or an info sheet that takes the place
of the one before, and a file another domain links to (a newsletter's file) —
passes `_process_document`, which checks the content: a PDF must carry the PDF
marker in its header, an image is decoded. A file
that is not what it says is refused with the door's sentence for a refused file,
`<file name>: <reason>`; a good document still lands.

Broken on purpose (14 October 2026, put back): the marker check taken out of
`_process_document` → every "declared a PDF" test fails ("DID NOT RAISE").
"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

import app.main  # noqa: F401 — the handlers of the ports are loaded through the app
from app.domains.media.api import MediaAsset
from app.domains.media.models import MediaKind
from app.kernel.contracts.media import StoreFile
from app.kernel.ports import call
from tests.conftest import seed_activity_with_product
from tests.integration.test_media_pdf_preview import _pdf


def _png() -> bytes:
    out = BytesIO()
    Image.new("RGB", (60, 40), (30, 90, 200)).save(out, format="PNG")
    return out.getvalue()


#: What a file can be while its upload says something else.
NOT_A_PDF = {
    "a picture": _png(),
    "plain text": b"Dit is gewone tekst, geen PDF.\n" * 20,
    "a web page": b"<!doctype html><html><body><p>Hallo</p></body></html>",
}


def _store(db, kind: str, filename: str, content_type: str, content: bytes):
    activity_id = None
    if kind == "activity_poster":
        activity, _component, _product = seed_activity_with_product(db)
        activity_id = activity.id
    return call(
        StoreFile(
            kind=kind,
            filename=filename,
            content_type=content_type,
            content=content,
            activity_id=activity_id,
        ),
        db,
    )


@pytest.mark.parametrize("kind", ["activity_poster", "newsletter_file"])
@pytest.mark.parametrize("what", sorted(NOT_A_PDF))
def test_a_file_declared_a_pdf_is_checked_for_the_pdf_marker(db_session, kind, what):
    with pytest.raises(Exception) as refused:
        _store(db_session, kind, "bestand.pdf", "application/pdf", NOT_A_PDF[what])
    assert "bestand.pdf: Geen geldige PDF" in str(refused.value), str(refused.value)
    assert db_session.query(MediaAsset).filter(MediaAsset.title.like("bestand%")).count() == 0


@pytest.mark.parametrize("kind", ["activity_poster", "newsletter_file"])
def test_a_file_declared_a_picture_is_decoded_as_one(db_session, kind):
    """A PDF declared a PNG is refused as well."""
    with pytest.raises(Exception) as refused:
        _store(db_session, kind, "bestand.png", "image/png", _pdf())
    assert "bestand.png: Geen geldige afbeelding" in str(refused.value), str(refused.value)


@pytest.mark.parametrize("kind", ["activity_poster", "newsletter_file"])
@pytest.mark.parametrize("lead", [b"", b"\n\r\n"], ids=["at-the-start", "after-a-few-bytes"])
def test_a_pdf_still_lands(db_session, kind, lead):
    stored = _store(db_session, kind, "goed.pdf", "application/pdf", lead + _pdf())
    asset = db_session.get(MediaAsset, stored.asset_id)
    assert asset is not None and asset.content_type == "application/pdf"
    assert asset.kind in (MediaKind.ACTIVITY_POSTER, MediaKind.NEWSLETTER_FILE)
