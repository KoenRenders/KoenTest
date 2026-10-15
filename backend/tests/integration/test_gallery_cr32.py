"""CR-32 phase 4 (R20, F18): the gallery block — one album as a grid of its photos.

The album is the photo page's own (`media.api.list_albums`: an ARCHIVED activity
with photos); the block holds its id. The service refuses an activity that is no
album at the save; the renderer shows nothing on the site for an album that has
no photo (any more) and the reason in the preview.

Broken on purpose (15 October 2026): the check of `_check_references` taken out
→ a draft pointing at a live activity is saved; the render not asking
`list_albums` → a photo of a live activity shows; the `preview` branch dropped →
an empty album leaves no reason.
"""

import re
from datetime import date

import pytest

from app.domains.cms.models import CmsPage
from app.domains.cms.render import render_document
from app.domains.cms.schema import InvalidShape, validate_document
from app.domains.cms.service import save_draft

pytestmark = pytest.mark.ui_serverrendered


def _gallery(activity_id: int) -> dict:
    return {"type": "doc", "content": [{"type": "gallery", "attrs": {"activity_id": activity_id}}]}


def _album(db, name: str, *, archived: bool, photos: int):
    from app.domains.activities.models import Activity, ActivityDate
    from app.domains.media.models import MediaAsset

    activity = Activity(name=name, location="Voorbeeldplein 1")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2020 if archived else 2099, 5, 1)))
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    for order in range(photos):
        db.add(
            MediaAsset(
                kind="activity_photo",
                activity_id=activity.id,
                title=f"Foto {order + 1}",
                data=png,
                content_type="image/png",
                thumbnail=png,
                thumb_content_type="image/png",
                width=64,
                height=48,
                byte_size=len(png),
                sort_order=order,
                is_active=True,
            )
        )
    db.flush()
    return activity


def test_the_gallery_node_holds_an_activity_id_and_nothing_else():
    assert validate_document(_gallery(7))
    for bad in (0, -1, "7", None):
        with pytest.raises(Exception, match="gallery.activity_id"):
            validate_document(_gallery(bad))


def test_an_album_renders_as_a_grid_of_its_photos_that_open_the_photo(db_session):
    album = _album(db_session, "Zomerfeest", archived=True, photos=3)
    html = render_document(_gallery(album.id), db_session)
    assert html.startswith('<div class="prose-gallery">') and html.count("<a ") == 3
    assert (
        len(
            re.findall(r'<a href="/api/v1/media/\d+"[^>]*><img src="/api/v1/media/\d+/thumb"', html)
        )
        == 3
    )
    assert 'alt="Foto 1"' in html


def test_an_activity_that_is_no_album_renders_nothing_and_says_why_in_the_preview(db_session):
    live = _album(db_session, "Nog te komen", archived=False, photos=2)
    nothing = _album(db_session, "Zonder foto's", archived=True, photos=0)
    for activity in (live, nothing):
        assert render_document(_gallery(activity.id), db_session) == ""
        assert "geen foto's" in render_document(_gallery(activity.id), db_session, preview=True)


def test_the_save_refuses_an_activity_that_is_no_album_by_name(db_session):
    live = _album(db_session, "Nog te komen", archived=False, photos=2)
    page = CmsPage(title="Galerij", slug="galerij-cr32", content="<p>x</p>", is_published=True)
    db_session.add(page)
    db_session.flush()
    with pytest.raises(InvalidShape, match=f"Onbekend album: {live.id}"):
        save_draft(db_session, page.id, _gallery(live.id), commit=False)
    album = _album(db_session, "Zomerfeest", archived=True, photos=1)
    assert save_draft(db_session, page.id, _gallery(album.id), commit=False).draft_json


def test_the_photo_page_and_the_gallery_share_one_definition_of_an_album(db_session):
    from app.domains.media.api import list_albums

    album = _album(db_session, "Zomerfeest", archived=True, photos=1)
    _album(db_session, "Nog te komen", archived=False, photos=1)
    assert album.id in {a.id for a in list_albums(db_session)}
    assert "Nog te komen" not in {a.name for a in list_albums(db_session)}
