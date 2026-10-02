"""What the picker offers, and in which order (CR-15 phase 2, #1472; C6 tests 3, 4).

Measured on `media.api.pick_options`, the one source of the offer:

- **last year first** (test 3): for a record of a copied activity, the photos of
  the activities it was copied from come first, one group per predecessor,
  "Van <name> (<year>)"; an activity without predecessors has no such group;
- **search and filters** (test 4): `q` matches the title, the activity's name and
  a tag's name; `year` keeps activities dated in that year; the two combine;
- **the tree's branches**: an activity's photos, its posters (the only place a
  poster is offered), a tag with the tags below it;
- **kinds**: never a render or a newsletter file;
- **pages of 60**;
- **the picker fragment** (`/admin/media/kiezer`): the group on top, thumbnails
  that set the macro's choice, tree links that reload the fragment in the modal;
  and the picker lives on `/admin/design-system`.

Proven red against master `149d7d99`: the module does not import there —
`pick_options` does not exist.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.media.api import (
    PICK_PAGE_SIZE,
    create_tag,
    pick_options,
    tag_asset,
)
from app.domains.media.models import MediaAsset


def _activity(db, name: str, year: int, *, copied_from: Activity | None = None) -> Activity:
    activity = Activity(name=name, copied_from_id=copied_from.id if copied_from else None)
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(year, 12, 5)))
    db.commit()
    return activity


def _asset(db, title: str, *, kind="activity_photo", activity: Activity | None = None):
    asset = MediaAsset(
        kind=kind,
        activity_id=activity.id if activity else None,
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


def _titles(options) -> list[str]:
    return [item.title for group in options.groups for item in group.items]


def test_last_year_comes_first_as_its_own_group(db_session):
    """C6 test 3."""
    sint_2025 = _activity(db_session, "Sint", 2025)
    sint_2026 = _activity(db_session, "Sint", 2026, copied_from=sint_2025)
    _asset(db_session, "sint vorig jaar", activity=sint_2025)
    _asset(db_session, "pagina", kind="page_image")
    _asset(db_session, "eigen foto", activity=sint_2026)

    copied = pick_options(db_session, for_activity_id=sint_2026.id)
    plain = pick_options(db_session, for_activity_id=sint_2025.id)

    first = copied.groups[0]
    assert first.label == "Van Sint (2025)"
    assert [i.title for i in first.items] == ["sint vorig jaar"]
    assert "sint vorig jaar" not in [i.title for g in copied.groups[1:] for i in g.items]
    assert all(g.label == "" for g in plain.groups), "no predecessors, no such group"


def test_search_matches_title_activity_name_and_tag(db_session):
    """C6 test 4, the search half."""
    kerstmarkt = _activity(db_session, "Kerstmarkt", 2024)
    _asset(db_session, "kraampjes", activity=kerstmarkt)
    _asset(db_session, "kerstboom op het plein", kind="page_image")
    getagd = _asset(db_session, "lichtjes", kind="page_image")
    tag_asset(db_session, getagd.id, create_tag(db_session, "Kerstsfeer").id)
    _asset(db_session, "zomerfeest", kind="page_image")

    found = set(_titles(pick_options(db_session, q="kerst")))

    assert found == {"kraampjes", "kerstboom op het plein", "lichtjes"}


def test_the_year_keeps_that_years_activities_and_combines_with_search(db_session):
    """C6 test 4, the filter half."""
    oud = _activity(db_session, "Kerstmarkt", 2024)
    nieuw = _activity(db_session, "Kerstmarkt", 2025)
    zomer = _activity(db_session, "Zomerfeest", 2024)
    _asset(db_session, "markt 2024", activity=oud)
    _asset(db_session, "markt 2025", activity=nieuw)
    _asset(db_session, "zomer 2024", activity=zomer)
    _asset(db_session, "zonder activiteit", kind="page_image")

    assert set(_titles(pick_options(db_session, year=2024))) == {"markt 2024", "zomer 2024"}
    assert _titles(pick_options(db_session, year=2024, q="kerst")) == ["markt 2024"]


def test_the_branches_photos_posters_and_a_tag_with_its_children(db_session):
    sint = _activity(db_session, "Sint", 2026)
    _asset(db_session, "foto", activity=sint)
    _asset(db_session, "ontwerpbeeld", kind="design_image", activity=sint)
    _asset(db_session, "affiche", kind="activity_poster", activity=sint)
    jeugd = create_tag(db_session, "Jeugd")
    kamp = create_tag(db_session, "Kamp", parent_id=jeugd.id)
    tag_asset(db_session, _asset(db_session, "tenten", kind="page_image").id, kamp.id)

    assert set(_titles(pick_options(db_session, photos_of=sint.id))) == {"foto", "ontwerpbeeld"}
    assert _titles(pick_options(db_session, posters_of=sint.id)) == ["affiche"]
    assert _titles(pick_options(db_session, tag_id=jeugd.id)) == ["tenten"]
    assert "affiche" not in _titles(pick_options(db_session)), "a poster only under Affiches"


def test_never_a_render_or_a_newsletter_file(db_session):
    _asset(db_session, "render", kind="design_render")
    _asset(db_session, "bijlage", kind="newsletter_file")
    _asset(db_session, "logo", kind="sponsor")
    _asset(db_session, "beeld", kind="page_image")

    # A sponsor logo is a picture of the library and is offered since #1473.
    assert sorted(_titles(pick_options(db_session))) == ["beeld", "logo"]


def test_pages_of_sixty(db_session):
    for n in range(PICK_PAGE_SIZE + 5):
        _asset(db_session, f"beeld {n}", kind="page_image")

    first = pick_options(db_session, page=1)
    second = pick_options(db_session, page=2)

    assert (first.total, first.pages) == (PICK_PAGE_SIZE + 5, 2)
    assert len(_titles(first)) == PICK_PAGE_SIZE and len(_titles(second)) == 5
    assert not set(_titles(first)) & set(_titles(second))


def _login(client, db):
    from tests.conftest import SEEDED_ADMIN_EMAIL

    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


@pytest.mark.ui_serverrendered
def test_the_picker_fragment_offers_last_year_first_and_chooses(client, db_session):
    sint_2025 = _activity(db_session, "Sint", 2025)
    sint_2026 = _activity(db_session, "Sint", 2026, copied_from=sint_2025)
    oud = _asset(db_session, "sint vorig jaar", activity=sint_2025)
    _asset(db_session, "pagina", kind="page_image")
    _asset(db_session, "affiche", kind="activity_poster", activity=sint_2026)
    _login(client, db_session)

    page = client.get(f"/admin/media/kiezer?field=main_image&for_activity_id={sint_2026.id}").text

    assert page.index("Van Sint (2025)") < page.index("sint vorig jaar") < page.index(">pagina<")
    # #1474: a thumbnail announces the choice as `media-picked`, with its data.
    assert (
        f'data-id="{oud.id}" data-url="/api/v1/media/{oud.id}" data-thumb="/api/v1/media/{oud.id}/thumb"'
        in page
    )
    assert "$dispatch('media-picked', { ...$el.dataset })" in page
    assert 'hx-target="#mp-main_image"' in page, "every link reloads the fragment in the modal"
    assert "posters_of=" in page and "photos_of=" in page, "the tree's branches are links"


@pytest.mark.ui_serverrendered
def test_the_picker_lives_on_the_design_system_page(client, db_session):
    _login(client, db_session)

    page = client.get("/admin/design-system").text

    assert 'name="ds_afbeelding"' in page
    assert 'hx-get="/admin/media/kiezer?field=ds_afbeelding"' in page
    assert 'id="mp-ds_afbeelding"' in page


@pytest.mark.ui_serverrendered
def test_the_logos_branch_leads_to_one_kind(client, db_session):
    """#1473: Logo's in the tree, one link per kind, and `kind` keeps that kind.
    An unknown kind in the address is no branch: the whole library."""
    _asset(db_session, "sponsorlogo", kind="sponsor")
    _asset(db_session, "eigen logo", kind="tenant_logo")
    _asset(db_session, "pagina", kind="page_image")
    _login(client, db_session)

    whole = client.get("/admin/media/kiezer?field=f").text
    assert "Logo&#39;s" in whole or "Logo's" in whole
    assert "kind=sponsor" in whole and "kind=tenant_logo" in whole

    sponsors = client.get("/admin/media/kiezer?field=f&kind=sponsor").text
    assert "sponsorlogo" in sponsors
    assert "eigen logo" not in sponsors and ">pagina<" not in sponsors

    unknown = client.get("/admin/media/kiezer?field=f&kind=design_render").text
    assert "sponsorlogo" in unknown and ">pagina<" in unknown


@pytest.mark.ui_serverrendered
def test_a_search_with_every_year_chosen_answers(client, db_session):
    """#1474: the "Alle jaren" chip sends `year=` with every search. The route
    took the year as an int and refused that with a 422, so every search in the
    picker failed — the CMS dialog showed "Er ging iets mis". Red on that
    version: 422."""
    _asset(db_session, "kerstboom", kind="page_image")
    _asset(db_session, "zomerfeest", kind="page_image")
    _login(client, db_session)

    resp = client.get("/admin/media/kiezer?field=f&q=kerst&year=")

    assert resp.status_code == 200, resp.status_code
    assert "kerstboom" in resp.text and "zomerfeest" not in resp.text, "the search filters"
