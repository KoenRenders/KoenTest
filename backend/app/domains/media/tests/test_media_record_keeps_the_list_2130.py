"""#2130 — a picture's record page remembers the list it was opened from.

The edit moved from the library's card to a record page per picture (CR-11
phase 5, round 3b). Until then an edit replaced only the cards and carried the
filters as hidden fields, so the list stood as it was. The record has to do the
same across a page: a card links to its record with the list's address
(`terug`) — the branch, the year, the search, the use and the page — and the
record's way back, its save and its delete return to that address.

Also here: an upload of several files at once lands on the chosen branch.

Proven red (put back): `_list_address` made to drop the year → the first test
fails on the year in the card's link.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

from app.domains.media.api import MediaAsset, MediaKind, create_tag
from tests.integration.test_media_keeps_the_activity import _login, _png
from tests.integration.test_media_tree_takes_the_filters import _activity, _picture


def _card_href(html: str, asset_id: int) -> str:
    match = re.search(rf'href="(/admin/media/{asset_id}\?terug=[^"]+)" data-row-link', html)
    assert match, f"no link to the record of picture {asset_id}"
    return match.group(1).replace("&amp;", "&")


def _list_of(href: str) -> dict[str, list[str]]:
    terug = unquote(parse_qs(urlparse(href).query)["terug"][0])
    assert terug.startswith("/admin/media?")
    return parse_qs(urlparse(terug).query)


def test_the_record_keeps_the_branch_the_year_and_the_search(client, db_session):
    activity = _activity(db_session, "Kamp")
    photo = _picture(db_session, MediaKind.ACTIVITY_PHOTO, activity.id, title="kampvuur")
    db_session.commit()
    csrf = _login(client)
    filtered = f"/admin/media?kind=activity_photo&activity_id={activity.id}&year=2027&q=kamp"

    href = _card_href(client.get(filtered).text, photo.id)
    state = _list_of(href)
    assert state["kind"] == ["activity_photo"]
    assert state["activity_id"] == [str(activity.id)]
    assert state["year"] == ["2027"]
    assert state["q"] == ["kamp"]

    record = client.get(href).text
    way_back = re.search(r'data-way-back href="([^"]+)"', record).group(1).replace("&amp;", "&")
    assert parse_qs(urlparse(way_back).query) == state, "the way back is the list as it stood"

    terug = way_back
    saved = client.post(
        f"/admin/media/{photo.id}",
        data={"title": "kampvuur bij nacht", "is_active": "1", "terug": terug},
        headers={"X-CSRF-Token": csrf},
    )
    assert saved.status_code == 204
    again = client.get(saved.headers["HX-Redirect"]).text
    assert "kampvuur bij nacht" in again
    assert f'data-way-back href="{terug.replace("&", "&amp;")}"' in again, "kept after saving"

    gone = client.post(
        f"/admin/media/{photo.id}/verwijderen",
        data={"terug": terug},
        headers={"X-CSRF-Token": csrf},
    )
    assert gone.status_code == 204
    assert gone.headers["HX-Redirect"] == terug, "deleted: back to the same list"


def test_the_record_keeps_the_use_filter_and_the_page_of_alles(client, db_session):
    _picture(db_session, MediaKind.SPONSOR, title="logo")
    db_session.commit()
    _login(client)
    photo = db_session.query(MediaAsset).filter(MediaAsset.title == "logo").one()

    href = _card_href(client.get("/admin/media?kind=alles").text, photo.id)
    assert _list_of(href)["kind"] == ["alles"]


def test_a_record_opened_from_nowhere_leads_back_to_the_library(client, db_session):
    photo = _picture(db_session, MediaKind.SPONSOR, title="los")
    db_session.commit()
    _login(client)
    record = client.get(f"/admin/media/{photo.id}").text
    assert 'data-way-back href="/admin/media"' in record


def test_a_tag_s_list_is_kept_too(client, db_session):
    tag = create_tag(db_session, "Sfeer")
    photo = _picture(db_session, MediaKind.SPONSOR, title="sfeerbeeld")
    from app.domains.media.api import set_asset_tags

    set_asset_tags(db_session, photo.id, [tag.id])
    db_session.commit()
    _login(client)
    href = _card_href(client.get(f"/admin/media?tag={tag.id}").text, photo.id)
    assert _list_of(href)["tag"] == [str(tag.id)]


def test_several_files_at_once_land_on_the_chosen_branch(client, db_session):
    activity = _activity(db_session, "Feest")
    db_session.commit()
    csrf = _login(client)
    answer = client.post(
        "/admin/media",
        files=[
            ("files", ("een.png", _png(), "image/png")),
            ("files", ("twee.png", _png(), "image/png")),
        ],
        data={
            "kind": "activity_photo",
            "activity_id": str(activity.id),
            "filter_kind": "activity_photo",
            "filter_activity_id": str(activity.id),
            "filter_year": "2027",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert answer.status_code == 204, answer.text[:300]
    target = parse_qs(urlparse(answer.headers["HX-Redirect"]).query)
    assert target == {
        "kind": ["activity_photo"],
        "activity_id": [str(activity.id)],
        "year": ["2027"],
    }
    assert (
        db_session.query(MediaAsset)
        .filter(MediaAsset.activity_id == activity.id, MediaAsset.kind == MediaKind.ACTIVITY_PHOTO)
        .count()
        == 2
    )


def test_the_upload_form_takes_several_files(client, db_session):
    _login(client)
    form = client.get("/admin/media/nieuw?kind=sponsor").text
    field = form[form.index('accept="image/*" multiple ') :]
    assert 'id="me-files" name="files"' in field[: field.index("</label>")], "one input, multiple"
    assert "bestanden gekozen" in field
