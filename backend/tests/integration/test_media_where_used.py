"""CR-15 #1471 — "where used", refusing a delete while used, pictures that
outlive their activity and their design (§C4.4, §C4.7; C6 tests 5–7).

"Where used" is derived: media asks the Design Studio (the three picture slots
and the logo strip of every design) and the CMS (the page texts). Deleting a
picture that something still shows is refused, with the uses as links, and
there is no forced delete. A soft-deleted activity leaves its photos in the
library, labelled as such; a deleted design leaves its pictures.

Proven red by violation, one facade at a time: each of the three references
(a slot, a logo, a page) added to an unused picture turns its delete into a
refusal — `test_each_kind_of_reference_alone_refuses_the_delete`. Against
master `4d2d641f` the module does not import: there is no `uses_of`.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.activities.api import Activity, ActivityDate, list_activities
from app.domains.activities.service import delete_activity
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.cms.api import CmsPage
from app.domains.designstudio.api import create_design, delete_design
from app.domains.designstudio.models import DesignLogo
from app.domains.media.api import (
    MediaAsset,
    MediaFout,
    MediaInUse,
    MediaKind,
    delete_media,
    list_activity_photos,
    uses_of,
)
from tests import media_door
from tests.conftest import SEEDED_ADMIN_EMAIL
from tests.integration.test_designstudio_engine import PNG_2x2

pytestmark = pytest.mark.ui_serverrendered


def _activity(db, name: str) -> Activity:
    activity = Activity(name=name, location="Miloheem")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2025, 6, 1)))
    db.flush()
    return activity


def _picture(db, kind=MediaKind.ACTIVITY_PHOTO, activity_id=None, title="foto") -> MediaAsset:
    asset = MediaAsset(
        kind=kind,
        activity_id=activity_id,
        data=PNG_2x2,
        content_type="image/png",
        thumbnail=PNG_2x2,
        thumb_content_type="image/png",
        width=2,
        height=2,
        byte_size=len(PNG_2x2),
        title=title,
        sort_order=0,
        is_active=True,
    )
    db.add(asset)
    db.flush()
    return asset


def _design(db, activity: Activity, **slots):
    design = create_design(
        db,
        activity_id=activity.id,
        duo_code="dark_green-golden_yellow",
        preset="beeld",
        created_by="bestuur@example.com",
    )
    for slot, asset_id in slots.items():
        setattr(design, slot, asset_id)
    db.flush()
    return design


def _page(db, title: str, asset_id: int, suffix: str = "") -> CmsPage:
    page = CmsPage(
        title=title,
        slug=title.lower().replace(" ", "-"),
        content=f'<p>Zo doe je het:</p><img src="/api/v1/media/{asset_id}{suffix}" alt="">',
    )
    db.add(page)
    db.flush()
    return page


def _count(db) -> int:
    return db.query(MediaAsset).count()


# ── C6 test 6: refuse while in use ──────────────────────────────────────────


def test_a_picture_on_a_design_and_a_page_is_used_twice_and_not_deleted(db_session):
    stappen = _activity(db_session, "Stappen en klappen")
    photo = _picture(db_session, activity_id=stappen.id)
    design = _design(db_session, stappen, main_image_id=photo.id)
    page = _page(db_session, "Lid worden", photo.id)

    uses = uses_of(db_session, photo.id)
    assert [(u.label, u.href) for u in uses] == [
        ("Ontwerp voor Stappen en klappen", f"/admin/ontwerpen/{design.id}"),
        ("Pagina Lid worden", f"/admin/paginas/{page.id}"),
    ]
    before = _count(db_session)
    with pytest.raises(MediaInUse) as refused:
        delete_media(db_session, photo.id)
    assert refused.value.uses == uses
    assert isinstance(refused.value, MediaFout), "a screen shows it like any input error"
    assert "Ontwerp voor Stappen en klappen" in str(refused.value)
    assert "Pagina Lid worden" in str(refused.value)
    assert _count(db_session) == before


@pytest.mark.parametrize("reference", ["slot", "logo", "page", "page_thumb"])
def test_each_kind_of_reference_alone_refuses_the_delete(db_session, reference):
    """The violation, added through each facade: unused, the picture deletes;
    with this one reference, the delete is refused."""
    activity = _activity(db_session, "Kerstmarkt")
    asset = _picture(db_session, kind=MediaKind.SPONSOR, title="logo")
    spare = _picture(db_session, kind=MediaKind.SPONSOR, title="reserve")
    if reference == "slot":
        _design(db_session, activity, inset_image_id=asset.id)
    elif reference == "logo":
        design = _design(db_session, activity)
        db_session.add(DesignLogo(design_id=design.id, media_asset_id=asset.id, sort_order=0))
        db_session.flush()
    else:
        _page(db_session, "Sponsors", asset.id, "/thumb" if reference == "page_thumb" else "")

    assert len(uses_of(db_session, asset.id)) == 1
    with pytest.raises(MediaInUse):
        delete_media(db_session, asset.id)
    assert uses_of(db_session, spare.id) == []
    delete_media(db_session, spare.id)
    assert db_session.get(MediaAsset, spare.id) is None


def test_a_page_with_a_longer_id_does_not_count_as_a_use(db_session):
    asset = _picture(db_session, kind=MediaKind.PAGE_IMAGE)
    other_id = int(f"{asset.id}7")
    _page(db_session, "Elders", other_id)
    assert uses_of(db_session, asset.id) == []


def test_the_json_route_answers_409_with_the_uses(client, db_session, admin_headers):
    activity = _activity(db_session, "Bowlen")
    photo = _picture(db_session, activity_id=activity.id)
    design = _design(db_session, activity, third_image_id=photo.id)
    db_session.commit()

    answer = media_door.delete(client, photo.id)
    assert answer.status_code == 409, answer.text
    assert answer.json()["detail"]["uses"] == [
        {"label": "Ontwerp voor Bowlen", "href": f"/admin/ontwerpen/{design.id}"}
    ]


def _board(client) -> str:
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return csrf_token_for(session)


def test_the_library_card_says_where_and_the_refusal_opens_it(client, db_session):
    activity = _activity(db_session, "Wandelen")
    photo = _picture(db_session, activity_id=activity.id, title="Op de dijk")
    design = _design(db_session, activity, main_image_id=photo.id)
    page = _page(db_session, "Wandelclub", photo.id)
    db_session.commit()
    csrf = _board(client)

    url = f"/admin/media?kind=activity_photo&activity_id={activity.id}"
    card = client.get(url).text
    assert "Gebruikt in 2" in card
    assert f'href="/admin/ontwerpen/{design.id}"' in card
    assert f'href="/admin/paginas/{page.id}"' in card
    assert '<details class="text-xs">' in card, "folded until clicked"

    refused = client.post(
        f"/admin/media/{photo.id}/verwijderen",
        data={"kind": "activity_photo", "q": "", "filter_activity_id": str(activity.id)},
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    assert refused.status_code == 200
    assert "Nog in gebruik in Ontwerp voor Wandelen, Pagina Wandelclub" in refused.text
    assert '<details class="text-xs" open>' in refused.text
    db_session.expire_all()
    assert db_session.get(MediaAsset, photo.id) is not None


def test_the_in_use_filter_shows_only_used_pictures_across_albums(client, db_session):
    one, two = _activity(db_session, "Album een"), _activity(db_session, "Album twee")
    used = _picture(db_session, activity_id=one.id, title="Gebruikte foto")
    _picture(db_session, activity_id=two.id, title="Ongebruikte foto")
    _design(db_session, two, main_image_id=used.id)
    db_session.commit()
    _board(client)

    everything = client.get("/admin/media?kind=activity_photo").text
    assert "Kies eerst een activiteit" in everything
    # In the tree column, under the year — not in the filter bar, which keeps
    # its one row (#1138) beside the tree of #1470.
    tree = everything[everything.index('id="me-boom"') :]
    tree = tree[: tree.index("</aside>")]
    assert 'name="gebruik"' in tree and 'name="year"' in tree
    assert everything.count('name="gebruik"') == 1
    in_use = client.get("/admin/media?kind=activity_photo&gebruik=in_gebruik").text
    assert "Gebruikte foto" in in_use and "Ongebruikte foto" not in in_use


# ── C6 test 7: pictures outlive their owner ─────────────────────────────────


def test_a_deleted_design_leaves_its_pictures(db_session):
    activity = _activity(db_session, "Quiz")
    photo = _picture(db_session, activity_id=activity.id)
    upload = _picture(db_session, kind=MediaKind.DESIGN_IMAGE, activity_id=activity.id)
    first = _design(db_session, activity, main_image_id=photo.id, inset_image_id=upload.id)
    _design(db_session, activity, main_image_id=photo.id)
    db_session.commit()
    assert len(uses_of(db_session, photo.id)) == 2

    before = _count(db_session)
    delete_design(db_session, first)
    assert _count(db_session) == before, "the design's pictures stay"
    assert len(uses_of(db_session, photo.id)) == 1
    assert uses_of(db_session, upload.id) == []


def test_a_deleted_activity_leaves_its_photos_labelled_in_the_library(client, db_session):
    gone = _activity(db_session, "Sinterklaas huisbezoeken")
    photos = [_picture(db_session, activity_id=gone.id, title=f"Sint {i}") for i in (1, 2)]
    db_session.commit()
    _board(client)
    assert "Sinterklaas huisbezoeken" in client.get("/fotos").text

    before = _count(db_session)
    assert delete_activity(db_session, gone.id)
    assert _count(db_session) == before, "soft-deleting the activity keeps its photos"

    library = client.get("/admin/media?kind=activity_photo").text
    assert "Sinterklaas huisbezoeken (verwijderd)" in library, "the filter still reaches it"
    album = client.get(f"/admin/media?kind=activity_photo&activity_id={gone.id}").text
    assert all(f"Sint {i}" in album for i in (1, 2))
    assert "Van een verwijderde activiteit" in album
    assert "Sinterklaas huisbezoeken" not in client.get("/fotos").text
    assert {p.id for p in photos} <= {p.id for p in db_session.query(MediaAsset).all()}


# ── C6 test 5: the album is untouched ───────────────────────────────────────


def test_a_photo_placed_on_another_activity_design_leaves_its_album(client, db_session):
    a, b = _activity(db_session, "Zomerfeest"), _activity(db_session, "Winterfeest")
    photo = _picture(db_session, activity_id=a.id, title="Zomer")
    db_session.commit()
    album_before = list_activity_photos(db_session, a.id)
    page_before = client.get(f"/activiteiten/{a.id}/fotos").text

    _design(db_session, b, main_image_id=photo.id)
    db_session.commit()

    assert list_activity_photos(db_session, a.id) == album_before
    assert list_activity_photos(db_session, b.id) == []
    page_after = client.get(f"/activiteiten/{a.id}/fotos").text
    assert f"/api/v1/media/{photo.id}" in page_after
    assert page_after.count("/api/v1/media/") == page_before.count("/api/v1/media/")
    assert a.id in {x.id for x in list_activities(db_session, scope="archived")}
