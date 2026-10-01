"""A copied design can choose last year's photos (#1397, second follow-up).

Koen, 1 October 2026, at the HDEV validation: the copied Design Studio design
points at the source's photos, but the photo choice showed only the media of the
copy — an empty list. A copy now remembers its source (`copied_from_id`), and the
photo choice offers the activity photos and design images of the activities
before it, under their own heading, as references. No file is copied.

Proven red against master `ee4fee11` (this file on an export of it): the copy
had no `copied_from_id`, and the copied design's photo choice held none of the
source's pictures.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.designstudio.models import Design
from app.domains.media.api import MediaAsset
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _media(db, kind: str, activity_id: int, title: str) -> MediaAsset:
    asset = MediaAsset(
        kind=kind,
        title=title,
        activity_id=activity_id,
        data=b"png",
        content_type="image/png",
        byte_size=3,
        sort_order=0,
    )
    db.add(asset)
    db.flush()
    return asset


def _login(client) -> str:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _copy(client, csrf, activity_id: int, start: date) -> int:
    answer = client.post(
        f"/admin/activiteiten/{activity_id}/kopieren",
        data={"start_date": start.isoformat()},
        headers={"X-CSRF-Token": csrf},
    )
    assert answer.status_code == 204, answer.text[:300]
    return int(answer.headers["HX-Redirect"].rsplit("/", 1)[1])


def test_the_copied_design_offers_the_source_photos_selected_and_nothing_is_copied(
    client, db_session
):
    source = Activity(name="Kerstherberg")
    db_session.add(source)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=source.id, start_date=date(2026, 12, 25)))
    photo = _media(db_session, "activity_photo", source.id, "Herberg vol")
    studio = _media(db_session, "design_image", source.id, "Kerstboom")
    db_session.add(
        Design(
            activity_id=source.id,
            duo_code="dark_green-golden_yellow",
            main_image_id=photo.id,
            inset_image_id=studio.id,
        )
    )
    db_session.commit()
    media_before = db_session.query(MediaAsset).count()
    csrf = _login(client)

    copy_id = _copy(client, csrf, source.id, date(2027, 12, 25))

    db_session.expire_all()
    design = db_session.query(Design).filter(Design.activity_id == copy_id).one()
    html = client.get(f"/admin/ontwerpen/{design.id}").text

    main = re.search(r'<select name="main_image_id".*?</select>', html, re.S).group(0)
    assert '<optgroup label="Van Kerstherberg (2026)">' in main, "the source's own heading"
    assert re.search(rf'<option value="{photo.id}" selected>', main), "the chosen photo"
    assert f'<option value="{studio.id}"' in main
    inset = re.search(r'<select name="inset_image_id".*?</select>', html, re.S).group(0)
    assert re.search(rf'<option value="{studio.id}" selected>', inset)
    assert db_session.query(MediaAsset).count() == media_before, "no file was copied"
    assert db_session.get(Activity, copy_id).copied_from_id == source.id


def test_the_chain_goes_back_nearest_first_and_never_round(db_session):
    from app.domains.activities.api import predecessors_of

    first = Activity(name="Bouwen")
    db_session.add(first)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=first.id, start_date=date(2025, 11, 15)))
    second = Activity(name="Bouwen", copied_from_id=first.id)
    db_session.add(second)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=second.id, start_date=date(2026, 11, 14)))
    third = Activity(name="Bouwen", copied_from_id=second.id)
    db_session.add(third)
    db_session.flush()

    chain = predecessors_of(db_session, third.id)

    assert [(p.id, p.year) for p in chain] == [(second.id, 2026), (first.id, 2025)]
    first.copied_from_id = third.id  # a circle, which a copy cannot make; still no loop
    db_session.flush()
    assert len(predecessors_of(db_session, third.id)) == 2
