"""The media library's tree, through the real screen (CR-15 phase 1, #1470; C6 test 9).

Measured on `/admin/media`:

- a tag with a child tag and two tagged pictures shows as a tree, and choosing a
  tag lists the pictures under it and under the tags below it — a picture with
  two tags under both;
- an activity with photos stands under *Activiteiten › its year › its name*
  without any tag row; its poster under *Affiches*, never among the album photos;
- the year filter keeps that year's activities, in the tree and in the list;
- a tag in use is not deleted, and the screen names how many pictures carry it;
- a card saves its tags, and an upload carries tags at once.

Proven red against master `4d2d641f`: the page has no tree and the tag routes
404.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.domains.activities.api import ActivityDate
from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.media.api import MediaAssetTag, create_tag, tag_asset, tags_of_assets
from app.domains.media.models import MediaAsset
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db) -> dict:
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value), "HX-Request": "true"}


def _asset(db, *, kind="page_image", title, activity_id=None):
    asset = MediaAsset(
        kind=kind,
        activity_id=activity_id,
        title=title,
        sort_order=0,
        is_active=True,
        content_type="image/jpeg",
        byte_size=10,
        width=10,
        height=10,
        data=b"x",
        thumbnail=b"y",
    )
    db.add(asset)
    db.commit()
    return asset


def _activity(db, name: str, year: int):
    activity, _c, _p = seed_activity_with_product(db)
    activity.name = name
    for d in list(activity.dates):
        db.delete(d)
    db.add(ActivityDate(activity_id=activity.id, start_date=date(year, 6, 1)))
    db.commit()
    return activity


def _tree(page: str) -> str:
    start = page.index('id="me-boom"')
    return page[start : page.index("</aside>", start)]


def _titles(page: str) -> set[str]:
    return set(re.findall(r'<img src="[^"]*" alt="([^"]*)"', page))


def test_the_tags_are_a_tree_and_a_picture_with_two_tags_is_under_both(client, db_session):
    jeugd = create_tag(db_session, "Jeugd")
    kamp = create_tag(db_session, "Kamp", parent_id=jeugd.id)
    sint = create_tag(db_session, "Sint")
    beide = _asset(db_session, title="kamp-met-sint")
    _asset(db_session, title="ongetagd")
    tag_asset(db_session, beide.id, kamp.id)
    tag_asset(db_session, beide.id, sint.id)
    _login(client, db_session)

    page = client.get("/admin/media").text
    tree = _tree(page)

    assert tree.index(">Jeugd<") < tree.index(">Kamp<"), "Kamp hangs under Jeugd"
    assert "border-l" in tree[tree.index(">Jeugd<") : tree.index(">Kamp<")], "a level deeper"
    for tag in (jeugd, kamp, sint):
        assert "kamp-met-sint" in _titles(client.get(f"/admin/media?tag={tag.id}").text), tag.name
    assert "ongetagd" not in _titles(client.get(f"/admin/media?tag={jeugd.id}").text)


def test_an_activity_and_its_poster_are_derived_branches(client, db_session):
    kermis = _activity(db_session, "Kermis 1470", 2026)
    _asset(db_session, kind="activity_photo", title="kermis-foto", activity_id=kermis.id)
    _asset(db_session, kind="activity_poster", title="kermis-affiche", activity_id=kermis.id)
    _login(client, db_session)

    tree = _tree(client.get("/admin/media").text)
    activiteiten = tree[tree.index(">Activiteiten<") : tree.index(">Affiches<")]
    affiches = tree[tree.index(">Affiches<") : tree.index(">Tags<")]
    assert ">2026<" in activiteiten and "Kermis 1470" in activiteiten
    assert ">2026<" in affiches and "Kermis 1470" in affiches
    assert db_session.query(MediaAssetTag).count() == 0, "no tag row behind the branch"

    album = client.get(f"/admin/media?kind=activity_photo&activity_id={kermis.id}").text
    posters = client.get(f"/admin/media?kind=activity_poster&activity_id={kermis.id}").text
    assert _titles(album) == {"kermis-foto"}, "the poster is not among the album photos"
    assert _titles(posters) == {"kermis-affiche"}


def test_the_year_filter_keeps_that_years_activities(client, db_session):
    oud = _activity(db_session, "Wandeling 1470", 2025)
    nieuw = _activity(db_session, "Fietstocht 1470", 2026)
    for a in (oud, nieuw):
        _asset(db_session, kind="activity_photo", title=f"foto-{a.id}", activity_id=a.id)
    tag = create_tag(db_session, "Natuur")
    for a in (oud, nieuw):
        tag_asset(
            db_session, db_session.query(MediaAsset).filter_by(activity_id=a.id).one().id, tag.id
        )
    _login(client, db_session)

    tree = _tree(client.get("/admin/media?year=2026").text)
    in_tag = _titles(client.get(f"/admin/media?tag={tag.id}&year=2026").text)

    assert "Fietstocht 1470" in tree and "Wandeling 1470" not in tree
    assert in_tag == {f"foto-{nieuw.id}"}


def test_a_tag_in_use_is_not_deleted_and_the_screen_says_how_many(client, db_session):
    tag = create_tag(db_session, "Sponsors")
    for title in ("logo-a", "logo-b"):
        tag_asset(db_session, _asset(db_session, kind="sponsor", title=title).id, tag.id)
    headers = _login(client, db_session)

    answer = client.post(f"/admin/media/tags/{tag.id}/verwijderen", headers=headers)

    assert "hangt nog aan 2 foto" in answer.text
    assert "HX-Redirect" not in answer.headers


def test_a_tag_is_made_renamed_and_an_empty_one_deleted(client, db_session):
    headers = _login(client, db_session)

    made = client.post("/admin/media/tags", data={"name": "Pagina's"}, headers=headers)
    assert made.status_code == 204 and "tag=" in made.headers["HX-Redirect"]
    tag_id = int(made.headers["HX-Redirect"].rsplit("=", 1)[1])
    client.post(f"/admin/media/tags/{tag_id}", data={"name": "Webpagina's"}, headers=headers)
    assert ">Webpagina&#39;s<" in _tree(client.get("/admin/media").text)
    gone = client.post(f"/admin/media/tags/{tag_id}/verwijderen", headers=headers)
    assert gone.status_code == 204


def test_a_card_saves_its_tags(client, db_session):
    a, b = create_tag(db_session, "A"), create_tag(db_session, "B")
    asset = _asset(db_session, kind="sponsor", title="bakker")
    tag_asset(db_session, asset.id, a.id)
    headers = _login(client, db_session)

    client.post(
        f"/admin/media/{asset.id}",
        data={"kind": "sponsor", "title": "bakker", "tags_on_card": "1", "tag_ids": [str(b.id)]},
        headers=headers,
    )

    assert tags_of_assets(db_session, [asset.id])[asset.id] == [b.id]


def test_an_upload_carries_tags_at_once(client, db_session):
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (40, 20), (10, 80, 160)).save(buf, format="JPEG")
    a, b = create_tag(db_session, "Pagina's"), create_tag(db_session, "Jeugd")
    headers = _login(client, db_session)

    answer = client.post(
        "/admin/media",
        files={"files": ("beeld.jpg", buf.getvalue(), "image/jpeg")},
        data={"kind": "page_image", "title": "met-twee-tags", "tag_ids": [str(a.id), str(b.id)]},
        headers=headers,
    )

    assert answer.status_code == 204, answer.text[:300]
    db_session.expire_all()
    asset = db_session.query(MediaAsset).filter(MediaAsset.title == "met-twee-tags").one()
    assert sorted(tags_of_assets(db_session, [asset.id])[asset.id]) == sorted([a.id, b.id])
