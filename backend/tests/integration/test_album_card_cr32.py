"""CR-32 phase 6 (R13, R14, F13, C6 14): the album card — ONE photo card that
moves through the latest albums, one photo at a time.

Broken on purpose (15 October 2026), each red for its own reason: the card
rendering a card per album instead of one → the one-card test fails; `photos`
ignored → the frames hold every photo; `interval` 0 still writing the Alpine state
→ the still test fails; the preview not forcing it still → the preview test fails;
an album without a photo not skipped → the empty-album test fails.
"""

import json
import re
from datetime import date

import pytest

from app.domains.cms.render import render_document
from app.domains.cms.schema import UnknownAttribute, validate_document

pytestmark = pytest.mark.ui_serverrendered


def _doc(**attrs) -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "albums", "attrs": {"albums": 3, "photos": 4, "interval": 3, **attrs}}
        ],
    }


def _album(db, name: str, year: int, photos: int):
    from app.domains.activities.models import Activity, ActivityDate
    from app.domains.media.models import MediaAsset

    activity = Activity(name=name, location="Voorbeeldplein 1")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(year, 6, 1)))
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    for order in range(photos):
        db.add(
            MediaAsset(
                kind="activity_photo",
                activity_id=activity.id,
                title=f"{name} {order + 1}",
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


def _frames(html: str) -> list[dict]:
    raw = re.search(r"frames: (\[.*?\]), i: 0", html, re.S).group(1)
    return json.loads(raw.replace("\\u0027", "'"))


def test_the_node_holds_three_numbers_in_their_ranges():
    assert validate_document(_doc())
    assert validate_document(_doc(albums=6, photos=8, interval=0))
    for field, bad in (
        ("albums", 0),
        ("albums", 7),
        ("photos", 9),
        ("interval", 1),
        ("interval", 11),
    ):
        with pytest.raises(UnknownAttribute, match=f"albums.{field}={bad}"):
            validate_document(_doc(**{field: bad}))


def test_one_card_moves_through_the_latest_albums_photo_by_photo(db_session):
    old = _album(db_session, "Oud feest", 2018, 2)
    mid = _album(db_session, "Middenfeest", 2020, 3)
    new = _album(db_session, "Nieuw feest", 2022, 2)
    html = render_document(_doc(albums=2, photos=2, interval=3), db_session)
    assert html.count("data-photo-card") == 1, "one card, not one per album"
    frames = _frames(html)
    # The two latest albums, at most two photos of each, the cover of the newest first.
    assert [f["name"] for f in frames] == ["Nieuw feest"] * 2 + ["Middenfeest"] * 2
    assert frames[0]["href"] == f"/activiteiten/{new.id}/fotos"
    assert frames[2]["href"] == f"/activiteiten/{mid.id}/fotos"
    assert old.id not in {int(f["href"].split("/")[2]) for f in frames}
    assert "x-data=" in html and "3000" in html
    assert 'href="/activiteiten/%d/fotos"' % new.id in html, "the server draws the first frame"
    assert "Nieuw feest" in html


def test_interval_zero_stands_still_and_the_preview_never_moves(db_session):
    _album(db_session, "Stilstaand", 2021, 3)
    still = render_document(_doc(interval=0), db_session)
    assert "x-data" not in still and "data-photo-card" in still
    preview = render_document(_doc(interval=3), db_session, preview=True)
    assert "x-data" not in preview and "data-photo-card" in preview


def test_a_single_photo_has_nothing_to_move_to(db_session):
    """Only the newest album, one photo: one frame, so no Alpine state."""
    _album(db_session, "Eén foto", 2023, 1)
    html = render_document(_doc(albums=1, photos=4, interval=3), db_session)
    assert "x-data" not in html and "Eén foto" in html


def test_no_album_is_nothing_on_the_site_and_its_reason_in_the_preview(db_session, monkeypatch):
    import app.domains.media.api as media

    monkeypatch.setattr(media, "list_albums", lambda db: [])
    assert render_document(_doc(), db_session) == ""
    assert "geen album met foto's" in render_document(_doc(), db_session, preview=True)


def test_the_macro_is_the_photo_pages_own(db_session):
    """No second card: the album card and the photo page's card are one macro with
    the same markup around the one picture slot."""
    from app.ui import templates

    macro = templates.env.get_template("_public_macros.html").module.photo_card
    plain = str(macro("Naam", "/x", "/y.png", date(2020, 6, 1)))
    moving = str(
        macro(
            "Naam",
            "/x",
            "/y.png",
            None,
            frames=[{"src": "/a", "name": "A", "date": "1 jun", "href": "/a"}] * 2,
            interval=3,
            date_text="1 jun",
        )
    )
    assert plain.count("<img") == 1 and moving.count("<img") == 1
    for marker in ("data-photo-card", "aspect-video", "object-cover", "font-semibold"):
        assert marker in plain and marker in moving
    assert ":src=" in moving and ":src=" not in plain
