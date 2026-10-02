"""#1473 — moving the 14 places behind `media.api` changes nothing a visitor
sees: the same address, the same bytes. A sample, as agreed: the site logo,
an activity's poster, a sponsor logo in the footer, and the bytes themselves,
each against the literal address the code wrote before the move.
"""

from __future__ import annotations

import pytest

from app.domains.activities.api import Activity
from app.domains.media.api import MediaAsset, MediaKind, asset_bytes, media_url
from tests.integration.test_designstudio_engine import PNG_2x2

pytestmark = pytest.mark.ui_serverrendered


def _asset(db, kind, **extra) -> MediaAsset:
    asset = MediaAsset(
        kind=kind,
        data=PNG_2x2,
        content_type="image/png",
        byte_size=len(PNG_2x2),
        title=str(kind),
        sort_order=0,
        is_active=True,
        **extra,
    )
    db.add(asset)
    db.flush()
    return asset


def test_media_url_writes_the_address_as_before():
    assert media_url(7) == "/api/v1/media/7"
    assert media_url(7, thumb=True) == "/api/v1/media/7/thumb"
    assert media_url(7, base_url="https://site.example") == "https://site.example/api/v1/media/7"


def test_the_site_logo_and_a_sponsor_have_the_same_address(client, db_session):
    logo = _asset(db_session, MediaKind.TENANT_LOGO)
    sponsor = _asset(db_session, MediaKind.SPONSOR, show_in_footer=True)
    db_session.commit()

    from app.ui import site_context

    assert site_context(db_session)["site_logo_url"] == f"/api/v1/media/{logo.id}"
    assert f'<img src="/api/v1/media/{sponsor.id}"' in client.get("/").text


def test_an_activity_poster_has_the_same_address(db_session):
    activity = Activity(name="Affichetest")
    db_session.add(activity)
    db_session.flush()
    poster = _asset(db_session, MediaKind.ACTIVITY_POSTER, activity_id=activity.id)
    db_session.expire_all()
    assert db_session.get(Activity, activity.id).poster_asset_url == f"/api/v1/media/{poster.id}"


def test_asset_bytes_are_the_stored_bytes(db_session):
    asset = _asset(db_session, MediaKind.PAGE_IMAGE)
    assert asset_bytes(db_session, asset.id) == PNG_2x2
    assert asset_bytes(db_session, asset.id + 100000) is None
