"""#1291 — the activity filter applies only to activity photos, and the server decides.

Koen: *"Nu zie je bvb. geen sponsors omdat er nog een activiteit als filter staat."*
Choose an activity among the activity photos, switch the kind to sponsors, and the
activity kept travelling with every request: `_lijst_ctx` passed it to `list_media`
whatever the kind, and sponsors hang off no activity, so the list came back empty.

The rule already existed in one place — `_filterstand` left the activity out of
"where I was" for any other kind — and the list did not follow it. Now both ask
`_activity_filter`, and these tests hold the list to it:

- the context of a sponsor list carries no activity, and all sponsors are in it;
- a URL with `kind=sponsor&activity_id=…` shows all sponsors: the server decides,
  not only the filter bar;
- the fragment the filter bar gets back carries the tree out-of-band and, since
  #1527, no activity list: the tree chooses the activity;
- and the activity filter still works where it belongs.

Proven red (29 September 2026):

- against the media code of master `e1a9a76e`: the context, URL and fragment tests
  fail with an empty sponsor list (`assert 3 is None` on the context); the
  activity-photo test passes, as it should;
- on this branch, additively: the raw `activity_id` re-applied after the
  `_activity_filter` call → the same three fail; `oob_uploadknop = False` added in
  `_lijst_response` → the fragment test fails with "the fragment does not replace
  the activity list".
"""

import pytest
from starlette.requests import Request

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.media.admin_ui import _lijst_ctx
from app.domains.media.models import MediaAsset
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

FRAGMENT = {"HX-Request": "true", "X-Raak-Filter": "1"}


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _asset(db, *, kind, activity_id=None, title):
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
    db.flush()
    return asset


@pytest.fixture
def media(db_session):
    """Two real activities with a photo each (the activity list shows only
    activities that exist and have media), and two sponsors."""
    first, _c, _p = seed_activity_with_product(db_session)
    second, _c, _p = seed_activity_with_product(db_session)
    _asset(db_session, kind="activity_photo", activity_id=first.id, title="album-elf")
    _asset(db_session, kind="activity_photo", activity_id=second.id, title="album-twaalf")
    _asset(db_session, kind="sponsor", title="sponsor-bakker")
    _asset(db_session, kind="sponsor", title="sponsor-garage")
    return first.id


def _request(query: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/admin/media",
            "query_string": query.encode(),
            "headers": [],
        }
    )


def test_the_context_of_a_sponsor_list_carries_no_activity(db_session, media):
    ctx = _lijst_ctx(_request(f"kind=sponsor&activity_id={media}"), db_session, kind="sponsor")

    assert ctx["activity_id"] is None
    titles = {a["title"] for a in ctx["assets"]}
    assert {"sponsor-bakker", "sponsor-garage"} <= titles, titles
    assert ctx["gefilterd"] is False, "an activity that does not apply counts as a filter"
    assert "activity_id" not in ctx["filterstand"]


def test_the_activity_filter_still_works_for_activity_photos(db_session, media):
    ctx = _lijst_ctx(
        _request(f"kind=activity_photo&activity_id={media}"), db_session, kind="activity_photo"
    )

    assert ctx["activity_id"] == media
    assert [a["title"] for a in ctx["assets"]] == ["album-elf"]
    assert f"activity_id={media}" in ctx["filterstand"]


def test_a_url_with_an_activity_shows_all_sponsors(client, db_session, media):
    _login(client, db_session)
    page = client.get(f"/admin/media?kind=sponsor&activity_id={media}").text

    assert "sponsor-bakker" in page and "sponsor-garage" in page


def test_the_fragment_carries_the_tree_and_no_activity_list(client, db_session, media):
    """#1527: the activity list is gone — the tree chooses the activity — so the
    fragment no longer replaces it; it replaces the tree, which follows."""
    _login(client, db_session)

    sponsors = client.get(f"/admin/media?kind=sponsor&activity_id={media}", headers=FRAGMENT).text
    assert "sponsor-bakker" in sponsors and "sponsor-garage" in sponsors
    assert 'id="media-activity-filter"' not in sponsors
    tree = sponsors.split('id="me-boom"', 1)
    assert len(tree) == 2 and 'hx-swap-oob="true"' in tree[1].split(">", 1)[0]
