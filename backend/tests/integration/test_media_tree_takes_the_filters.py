"""#1527 — the tree of /admin/media takes over the kind and the activity lists,
and "+ Uploaden" starts from the chosen branch.

- The library and the picker list the same kind branches — Logo's (sponsor,
  association logo), Paginabeelden, Ontwerpbeelden — from one source,
  `media.api.KIND_GROUPS`.
- Landing shows no list ("Kies een tak", #891 kept); "Alles" is a choice: every
  kind, in pages of 60, without the arrows.
- "+ Uploaden" carries the branch: an album's activity, a kind, a tag — visible
  and changeable on the form; on Affiches it leads to the activity's own poster
  screen. After the upload, back on that branch.

Proven red against master `fcb88be1`: seven of the ten fail — the library tree
has no kind branches and no "Alles", landing shows the photos' "Kies eerst", there
are no pages, the tag is no starting point of the form, Affiches has no way to
the poster screen, and an upload returns neither to its tag nor, from another
branch, to its own place. The other three (an album's or a sponsor's start, the
return to an album) held already and keep holding.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.media.api import MediaAsset, MediaKind, create_tag
from tests.integration.test_media_keeps_the_activity import _login, _png
from tests.integration.test_media_where_used import PNG_2x2

pytestmark = pytest.mark.ui_serverrendered

FRAGMENT = {"HX-Request": "true"}


def _activity(db, name: str) -> Activity:
    activity = Activity(name=name, location="Miloheem")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2027, 6, 1)))
    db.flush()
    return activity


def _picture(db, kind, activity_id=None, title="beeld") -> MediaAsset:
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


def _kind_branches(html: str) -> set[str]:
    return set(re.findall(r"kind=(sponsor|tenant_logo|page_image)\b", html))


def test_the_library_and_the_picker_list_the_same_kind_branches(client, db_session):
    _login(client)

    library = client.get("/admin/media").text
    picker = client.get("/admin/media/kiezer?field=f").text

    expected = {"sponsor", "tenant_logo", "page_image"}
    assert _kind_branches(library) == expected
    assert _kind_branches(picker) == expected
    for name in ("Logo&#39;s", "Paginabeelden", "Ontwerpbeelden", "Zonder activiteit"):
        assert name in library and name in picker, name


def test_ontwerpbeelden_branch_per_activity_and_without_one(client, db_session):
    """Koen's addition to #1527: Ontwerpbeelden › year › activity, like Affiches,
    from the picture's activity; a design picture of no activity under
    "Zonder activiteit". The library and the picker both."""
    activity = _activity(db_session, "Ontwerpdag")
    with_one = _picture(db_session, MediaKind.DESIGN_IMAGE, activity.id, "ontwerp-met")
    without = _picture(db_session, MediaKind.DESIGN_IMAGE, None, "ontwerp-zonder")
    db_session.commit()
    _login(client)

    library = client.get("/admin/media").text
    assert f"/admin/media?kind=design_image&amp;activity_id={activity.id}" in library
    assert "/admin/media?kind=design_image&amp;activity_id=0" in library

    album = client.get(f"/admin/media?kind=design_image&activity_id={activity.id}").text
    loose = client.get("/admin/media?kind=design_image&activity_id=0").text
    assert "ontwerp-met" in album and "ontwerp-zonder" not in album
    assert "ontwerp-zonder" in loose and "ontwerp-met" not in loose

    picked = client.get(f"/admin/media/kiezer?field=f&designs_of={activity.id}").text
    picked_loose = client.get("/admin/media/kiezer?field=f&designs_of=0").text
    assert f'data-id="{with_one.id}"' in picked and f'data-id="{without.id}"' not in picked
    assert (
        f'data-id="{without.id}"' in picked_loose and f'data-id="{with_one.id}"' not in picked_loose
    )

    form = client.get(f"/admin/media/nieuw?kind=design_image&activity_id={activity.id}").text
    assert 'value="design_image" selected' in form
    assert f'value="{activity.id}" selected' in form


def test_landing_shows_no_list_and_alles_shows_every_kind(client, db_session):
    activity = _activity(db_session, "Kerstmarkt")
    photo = _picture(db_session, MediaKind.ACTIVITY_PHOTO, activity.id, "kerstfoto")
    _picture(db_session, MediaKind.SPONSOR, title="bakker-logo")
    _picture(db_session, MediaKind.DESIGN_IMAGE, activity.id, "ontwerp-beeld")
    db_session.commit()
    _login(client)

    landing = client.get("/admin/media").text
    assert "Kies een tak in de boom" in landing and "kerstfoto" not in landing

    alles = client.get("/admin/media?kind=alles").text
    for title in ("kerstfoto", "bakker-logo", "ontwerp-beeld"):
        assert title in alles, title
    assert f"/admin/media/{photo.id}/verplaats" not in alles, "no arrows in Alles"


def test_alles_pages_by_sixty(client, db_session):
    for n in range(65):
        _picture(db_session, MediaKind.PAGE_IMAGE, title=f"pagina-{n:02d}")
    db_session.commit()
    _login(client)

    first = client.get("/admin/media?kind=alles", headers=FRAGMENT).text
    second = client.get("/admin/media?kind=alles&page=2", headers=FRAGMENT).text

    on_first = set(re.findall(r"pagina-\d\d", first))
    on_second = set(re.findall(r"pagina-\d\d", second))
    assert len(on_first) == 60 and len(on_second) == 5
    assert not on_first & on_second
    assert "1–60 van 65" in first


@pytest.mark.parametrize(
    ("query", "selected"),
    [
        (
            "kind=activity_photo&activity_id={activity}",
            ['value="activity_photo" selected', 'value="{activity}" selected'],
        ),
        ("kind=sponsor", ['value="sponsor" selected']),
        ("tag={tag}", ['value="activity_photo" selected']),
    ],
)
def test_the_upload_form_starts_from_the_branch(client, db_session, query, selected):
    activity = _activity(db_session, "Wandeling")
    tag = create_tag(db_session, "Zomer")
    db_session.commit()
    _login(client)

    form = client.get("/admin/media/nieuw?" + query.format(activity=activity.id, tag=tag.id)).text

    for needle in selected:
        assert needle.format(activity=activity.id) in form, needle
    if "tag=" in query:
        assert f'name="filter_tag" value="{tag.id}"' in form
        assert re.search(rf'name="tag_ids" value="{tag.id}"[^>]*checked', form), "the tag is chosen"


def test_on_affiches_upload_leads_to_the_activity_poster_screen(client, db_session):
    activity = _activity(db_session, "Quiz")
    _picture(db_session, MediaKind.ACTIVITY_POSTER, activity.id, "affiche")
    db_session.commit()
    _login(client)

    page = client.get(f"/admin/media?kind=activity_poster&activity_id={activity.id}").text

    assert f'href="/admin/activiteiten/{activity.id}"' in page
    assert "/admin/media/nieuw?kind=activity_poster" not in page


@pytest.mark.parametrize("branch", ["album", "tag", "elsewhere"])
def test_an_upload_returns_to_its_branch(client, db_session, branch):
    activity = _activity(db_session, "Fietstocht")
    tag = create_tag(db_session, "Fietsen")
    db_session.commit()
    csrf = _login(client)
    data = {"kind": "activity_photo", "activity_id": str(activity.id), "q": ""}
    if branch == "album":
        data.update(filter_kind="activity_photo", filter_activity_id=str(activity.id))
    elif branch == "tag":
        data.update(filter_kind="", filter_tag=str(tag.id), tag_ids=str(tag.id))
    else:  # from the sponsors, the user changed the kind on the form
        data.update(filter_kind="sponsor")

    answer = client.post(
        "/admin/media",
        data=data,
        files={"files": ("foto.png", _png(), "image/png")},
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )

    assert answer.status_code == 204, answer.text[:300]
    back = answer.headers["HX-Redirect"]
    expected = {
        "album": f"/admin/media?kind=activity_photo&activity_id={activity.id}",
        "tag": f"/admin/media?tag={tag.id}",
        "elsewhere": f"/admin/media?kind=activity_photo&activity_id={activity.id}",
    }[branch]
    assert back == expected
