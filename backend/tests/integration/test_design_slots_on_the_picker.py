"""CR-15 #1473 — the Design Studio's slots on the picker (C6 test 1).

Choosing stores nothing: a slot holds the id of a library picture — now also
an album photo of another activity — and no media row is added. Uploading in
the studio adds exactly one, at the one size of 2 400 px. A slot refuses what
the picker would not offer: a render, a PDF, another tenant's picture.

Proven red against master `7dc180e0`: there `save_design` stored any id it was
sent, so the refusals did not happen, and the editor offered only this
activity's and its predecessors' photos — another activity's photo was not in
its select. On this branch, with `set_slot_image`'s check taken out, the three
refusal cases fail.
"""

from __future__ import annotations

import io
from datetime import date

import pytest
from PIL import Image

from app.domains.activities.api import Activity, ActivityDate
from app.domains.designstudio.api import DesignError, create_design, save_design
from app.domains.media.api import MediaAsset, MediaKind, offered_by_picker, pick_options
from app.kernel.codes import code_of
from tests.integration.test_designstudio_engine import PNG_2x2

pytestmark = pytest.mark.ui_serverrendered


def _activity(db, name: str) -> Activity:
    activity = Activity(name=name, location="Miloheem")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2025, 5, 1)))
    db.flush()
    return activity


def _asset(db, kind, *, activity_id=None, content_type="image/png", tenant_id=None) -> MediaAsset:
    asset = MediaAsset(
        kind=kind,
        activity_id=activity_id,
        data=PNG_2x2,
        content_type=content_type,
        thumbnail=PNG_2x2,
        thumb_content_type="image/png",
        width=2,
        height=2,
        byte_size=len(PNG_2x2),
        title=f"{kind}",
        sort_order=0,
        is_active=True,
    )
    if tenant_id is not None:
        asset.tenant_id = tenant_id
    db.add(asset)
    db.flush()
    return asset


def _design(db, activity):
    return create_design(
        db,
        activity_id=activity.id,
        duo_code="dark_green-golden_yellow",
        preset="beeld",
        created_by="bestuur@example.com",
    )


def _save(db, design, **slots):
    form = {"duo_code": design.duo_code, "preset": code_of(design.preset)}
    form.update({k: str(v) for k, v in slots.items()})
    save_design(db, design, form, highlights=[], logo_ids=[])


def _counts(db) -> tuple[int, int]:
    total = db.query(MediaAsset).count()
    images = db.query(MediaAsset).filter(MediaAsset.kind == MediaKind.DESIGN_IMAGE).count()
    return total, images


def test_another_activitys_album_photo_is_a_reference_and_stores_nothing(db_session):
    winter = _activity(db_session, "Winterwandeling")
    zomer = _activity(db_session, "Zomerfeest")
    photo = _asset(db_session, MediaKind.ACTIVITY_PHOTO, activity_id=zomer.id)
    design = _design(db_session, winter)

    offered = {
        item.id
        for group in pick_options(db_session, for_activity_id=winter.id).groups
        for item in group.items
    }
    assert photo.id in offered, "the picker offers the whole library"

    before = _counts(db_session)
    _save(db_session, design, main_image_id=photo.id, inset_image_id=photo.id)
    assert (design.main_image_id, design.inset_image_id) == (photo.id, photo.id)
    assert _counts(db_session) == before, "no media row and no design image added"
    assert db_session.get(MediaAsset, photo.id).activity_id == zomer.id, "it stays in its album"


def test_emptying_a_slot_stores_none(db_session):
    activity = _activity(db_session, "Quiz")
    photo = _asset(db_session, MediaKind.ACTIVITY_PHOTO, activity_id=activity.id)
    design = _design(db_session, activity)
    _save(db_session, design, third_image_id=photo.id)
    _save(db_session, design, third_image_id="")
    assert design.third_image_id is None


@pytest.mark.parametrize("case", ["render", "pdf poster", "other tenant"])
def test_a_slot_refuses_what_the_picker_would_not_offer(db_session, case):
    activity = _activity(db_session, "Bowlen")
    design = _design(db_session, activity)
    if case == "render":
        asset = _asset(db_session, MediaKind.DESIGN_RENDER, activity_id=activity.id)
    elif case == "pdf poster":
        asset = _asset(
            db_session,
            MediaKind.ACTIVITY_POSTER,
            activity_id=activity.id,
            content_type="application/pdf",
        )
    else:
        asset = _asset(db_session, MediaKind.PAGE_IMAGE, tenant_id=3)
    db_session.expire_all()

    # As in a request: the middleware sets the tenant, and the ORM filter then
    # hides another tenant's rows (outside a request nothing is filtered).
    from app.kernel.tenancy import TENANT_MILLEGEM_ID, current_tenant_id

    token = current_tenant_id.set(TENANT_MILLEGEM_ID)
    try:
        assert not offered_by_picker(db_session, asset.id)
        with pytest.raises(DesignError, match="kan niet in een beeldvak"):
            _save(db_session, design, main_image_id=asset.id)
    finally:
        current_tenant_id.reset(token)
    assert design.main_image_id is None, "refused before anything changed"


def _offered(db, **branch) -> set[int]:
    return {item.id for group in pick_options(db, **branch).groups for item in group.items}


@pytest.mark.parametrize("kind", [MediaKind.SPONSOR, MediaKind.TENANT_LOGO])
def test_a_logo_is_offered_in_its_branch_and_can_be_stored(db_session, kind):
    """Everything in the library that is a picture can be chosen (#1473): the
    logos hang off no activity, so they have a branch of their own (Logo's).
    Red before: neither kind was in PICKABLE_KINDS, so not offered and refused."""
    activity = _activity(db_session, "Kaartavond")
    logo = _asset(db_session, kind)
    photo = _asset(db_session, MediaKind.ACTIVITY_PHOTO, activity_id=activity.id)
    design = _design(db_session, activity)

    assert logo.id in _offered(db_session), "offered in the whole library"
    branch = _offered(db_session, kind=kind)
    assert logo.id in branch and photo.id not in branch, "its branch holds that kind only"

    _save(db_session, design, main_image_id=logo.id)
    assert design.main_image_id == logo.id


def test_the_posters_branch_offers_a_poster_only_as_a_picture(db_session):
    """A PDF poster cannot go into a slot, so the picker does not show it (#1473):
    the offer and the slot check are one condition (`_offered`). Red before:
    the branch listed every poster and a PDF was refused only on saving."""
    activity = _activity(db_session, "Affichewedstrijd")
    picture = _asset(db_session, MediaKind.ACTIVITY_POSTER, activity_id=activity.id)
    pdf = _asset(
        db_session,
        MediaKind.ACTIVITY_POSTER,
        activity_id=activity.id,
        content_type="application/pdf",
    )

    branch = _offered(db_session, posters_of=activity.id)
    assert picture.id in branch, "a poster that is a picture is offered"
    assert pdf.id not in branch, "a PDF poster is not"
    assert offered_by_picker(db_session, picture.id)
    assert not offered_by_picker(db_session, pdf.id)


def test_an_upload_in_the_studio_adds_one_row_at_2400(client, db_session):
    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    activity = _activity(db_session, "Kerstmarkt")
    design = _design(db_session, activity)
    db_session.commit()
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    buffer = io.BytesIO()
    Image.new("RGB", (5000, 2500), (40, 90, 40)).save(buffer, "JPEG")

    before = _counts(db_session)
    answer = client.post(
        f"/admin/ontwerpen/{design.id}/afbeelding",
        files={"file": ("groot.jpg", buffer.getvalue(), "image/jpeg")},
        data={"slot": "main_image_id", "layout": "print_a"},
        headers={"X-CSRF-Token": csrf_token_for(session)},
    )
    assert answer.status_code in (200, 204, 303), answer.text[:200]
    db_session.expire_all()
    total, images = _counts(db_session)
    assert (total, images) == (before[0] + 1, before[1] + 1)
    stored = db_session.get(MediaAsset, db_session.get(type(design), design.id).main_image_id)
    assert (stored.width, stored.height) == (2400, 1200)
