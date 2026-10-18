"""#2142 — a design picture uploaded in Media needs an activity.

The branch "Ontwerpbeelden › Zonder activiteit" was empty on HDEV and PROD
(measured 18 October 2026): the Design Studio ties every design to an activity
and gives its pictures that activity, and the only way into the branch was an
upload in Media without one. Koen, to the proposal that the branch goes and an
uploaded design picture needs an activity: "ja, doe dat maar".

Proven red (put back): the activity check made to hold for activity photos only
again → the refusal test stores a picture and fails.
"""

from __future__ import annotations

import re

from app.domains.media.api import MediaAsset, MediaKind
from tests.integration.test_media_keeps_the_activity import _login, _png
from tests.integration.test_media_tree_takes_the_filters import _activity, _picture


def _upload(client, csrf, **data):
    return client.post(
        "/admin/media",
        files={"files": ("ontwerp.png", _png(), "image/png")},
        data={"kind": "design_image", "title": "ontwerp-2142", **data},
        headers={"X-CSRF-Token": csrf},
    )


def _stored(db) -> int:
    db.expire_all()
    return db.query(MediaAsset).filter(MediaAsset.title == "ontwerp-2142").count()


def test_without_an_activity_it_is_refused_at_the_field_and_nothing_is_stored(client, db_session):
    csrf = _login(client)
    answer = _upload(client, csrf, activity_id="")
    assert answer.status_code == 200, "the upload screen again, with the reason"
    field = answer.text[answer.text.index('data-field="activity_id"') :]
    field = field[: field.index('data-field="title"')]
    assert "Kies eerst een activiteit." in field, "the reason stands at the activity field"
    assert 'aria-invalid="true"' in field
    assert _stored(db_session) == 0


def test_with_an_activity_it_lands_in_that_activity_s_branch(client, db_session):
    activity = _activity(db_session, "Ontwerpavond")
    db_session.commit()
    csrf = _login(client)
    answer = _upload(
        client,
        csrf,
        activity_id=str(activity.id),
        filter_kind="design_image",
        filter_activity_id=str(activity.id),
    )
    assert answer.status_code == 204, answer.text[:300]
    assert answer.headers["HX-Redirect"] == (
        f"/admin/media?kind=design_image&activity_id={activity.id}"
    )
    assert _stored(db_session) == 1
    branch = client.get(answer.headers["HX-Redirect"]).text
    assert "ontwerp-2142" in branch


def test_the_upload_form_asks_the_activity_for_a_design_picture(client, db_session):
    _login(client)
    form = client.get("/admin/media/nieuw?kind=design_image").text
    assert re.search(
        r":required=\"soort === 'activity_photo' \|\| soort === 'design_image'\"", form
    )


def test_search_and_reorder_keep_the_design_branch(client, db_session):
    """Existing behaviour, inside an activity's design branch."""
    activity = _activity(db_session, "Ontwerpweek")
    first = _picture(db_session, MediaKind.DESIGN_IMAGE, activity.id, "eerste-ontwerp")
    _picture(db_session, MediaKind.DESIGN_IMAGE, activity.id, "tweede-ontwerp")
    db_session.commit()
    csrf = _login(client)

    searched = client.get(
        f"/admin/media?kind=design_image&activity_id={activity.id}&q=eerste",
        headers={"HX-Request": "true", "X-Raak-Filter": "1"},
    ).text
    assert "eerste-ontwerp" in searched and "tweede-ontwerp" not in searched

    moved = client.post(
        f"/admin/media/{first.id}/verplaats",
        data={
            "richting": "omlaag",
            "kind": "design_image",
            "filter_activity_id": str(activity.id),
        },
        headers={"X-CSRF-Token": csrf},
    ).text
    assert "eerste-ontwerp" in moved and "tweede-ontwerp" in moved
    assert "Kies een tak" not in moved, "the branch stays after a reorder"
