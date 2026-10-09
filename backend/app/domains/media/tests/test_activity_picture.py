"""The picture that stands for an activity in a letter (#984, #1019; #1251).

`activity_image_path` is a read: it answers with where the picture is, and makes
nothing. Until the media ports it also rendered a PDF poster's first page the
first time it was asked — for posters stored before #1019 gave every PDF its
picture at the store — and flushed that. Counted on 9 October 2026: PROD 36 PDF
posters, UAT 2, HDEV 10, and on all three not one without its stored rendering.
So the lazy branch left, with nothing to fill in first.

The four answers below were recorded with the lazy branch still there and are
the same without it.

Proven red (9 October 2026): the `/thumb` answer for a PDF returned without
asking whether a rendering exists → the PDF that cannot be rendered answers with
a path, and a mail would show a broken image.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

import app.main  # noqa: F401 — the handlers of the ports are loaded through the app
from app.domains.media.api import MediaAsset, activity_image_path
from app.kernel.contracts.media import StoreFile
from app.kernel.ports import call
from tests.conftest import seed_activity_with_product
from tests.integration.test_media_pdf_preview import _pdf

pytestmark = pytest.mark.ui_agnostisch


def _png() -> bytes:
    out = BytesIO()
    Image.new("RGB", (60, 40), (200, 30, 30)).save(out, format="PNG")
    return out.getvalue()


def _poster(db, activity_id: int, filename: str, content_type: str, content: bytes) -> int:
    stored = call(
        StoreFile(
            kind="activity_poster",
            filename=filename,
            content_type=content_type,
            content=content,
            activity_id=activity_id,
            title_base="Quiz - poster",
        ),
        db,
    )
    return stored.asset_id


def test_an_activity_without_a_poster_has_no_picture(db_session):
    activity, _component, _product = seed_activity_with_product(db_session)
    assert activity_image_path(db_session, activity.id) is None


def test_an_image_poster_is_its_own_picture(db_session):
    activity, _component, _product = seed_activity_with_product(db_session)
    asset_id = _poster(db_session, activity.id, "affiche.png", "image/png", _png())
    assert activity_image_path(db_session, activity.id) == f"/api/v1/media/{asset_id}"


def test_a_pdf_poster_answers_with_its_rendering(db_session):
    activity, _component, _product = seed_activity_with_product(db_session)
    asset_id = _poster(db_session, activity.id, "affiche.pdf", "application/pdf", _pdf())
    assert activity_image_path(db_session, activity.id) == f"/api/v1/media/{asset_id}/thumb"


def test_a_pdf_that_cannot_be_rendered_has_no_picture(db_session):
    """A file that says it is a PDF and holds no page: it is stored as a document
    and has no picture — a letter leaves the picture out instead of showing a
    broken one."""
    activity, _component, _product = seed_activity_with_product(db_session)
    asset_id = _poster(
        db_session, activity.id, "affiche.pdf", "application/pdf", b"%PDF-1.4\n%%EOF\n"
    )
    assert db_session.query(MediaAsset).filter(MediaAsset.id == asset_id).one().thumbnail is None
    assert activity_image_path(db_session, activity.id) is None


def test_asking_for_the_picture_writes_nothing(db_session):
    """A read: nothing new, nothing changed, nothing to flush — for the PDF that
    has no rendering too, which is where the lazy branch wrote."""
    activity, _component, _product = seed_activity_with_product(db_session)
    _poster(db_session, activity.id, "affiche.pdf", "application/pdf", b"%PDF-1.4\n%%EOF\n")
    db_session.flush()
    activity_image_path(db_session, activity.id)
    assert not db_session.new and not db_session.dirty
