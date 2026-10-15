"""CR-32 phase 3 (R6, F8): the favicon of a site is the newest picture of the
kind `site_icon` — one per tenant, as the logo is, no setting.

Koen, 15 October 2026 (#2003, on the favicon "zoals het logo"): "akkoord".
The typeface pair (R7) is not built (his "a"): no setting, no test of one.

Broken on purpose (15 October 2026), each red for its own reason: the shell
passing no `site_icon_url` → the tenant keeps the platform's icon; `tenant_site_icon`
ordering by the oldest → the older upload wins; the SVG exception widened to every
kind → the sponsor refusal test fails; the code row left out of the list → a
database without it refuses the upload.
"""

from io import BytesIO

import pytest
from PIL import Image

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.media.models import MediaAsset
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

SVG = "http://www.w3.org/2000/svg"
ICON_SVG = (
    f'<svg xmlns="{SVG}" viewBox="0 0 32 32"><rect width="32" height="32" fill="#0051a4"/></svg>'
)


def _login(client) -> str:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _png(size: int = 64) -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (size, size), (0, 81, 164, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _upload(
    client, data: bytes, *, kind="site_icon", name="icoon.png", ctype="image/png", title="Icoon"
):
    csrf = _login(client)
    return client.post(
        "/admin/media",
        files={"files": (name, data, ctype)},
        data={"kind": kind, "title": title},
        headers={"X-CSRF-Token": csrf},
    )


def _icon_links(html: str) -> list[str]:
    import re

    return re.findall(r'<link rel="icon" href="([^"]+)"', html)


def test_a_site_without_an_icon_keeps_the_platforms(client, db_session):
    links = _icon_links(client.get("/").text)
    assert len(links) == 1 and "favicon.ico" in links[0], links


def test_a_site_with_an_icon_shows_it_in_the_tab_and_not_the_platforms(client, db_session):
    response = _upload(client, _png())
    assert response.status_code in (200, 201, 204, 303), response.text[:200]
    db_session.expire_all()
    asset = db_session.query(MediaAsset).filter(MediaAsset.title == "Icoon").one()
    assert asset.kind.value == "site_icon"
    links = _icon_links(client.get("/").text)
    assert links == [f"/api/v1/media/{asset.id}"], links


def test_the_newest_icon_wins_and_the_older_one_is_left_alone(client, db_session):
    _upload(client, _png(48), title="Oud")
    _upload(client, _png(96), title="Nieuw")
    db_session.expire_all()
    newest = db_session.query(MediaAsset).filter(MediaAsset.title == "Nieuw").one()
    assert _icon_links(client.get("/").text) == [f"/api/v1/media/{newest.id}"]
    assert db_session.query(MediaAsset).filter(MediaAsset.title == "Oud").count() == 1


def test_an_svg_is_allowed_for_the_icon_and_still_refused_for_a_sponsor(client, db_session):
    ok = _upload(
        client, ICON_SVG.encode(), name="icoon.svg", ctype="image/svg+xml", title="SvgIcoon"
    )
    assert ok.status_code in (200, 201, 204, 303), ok.text[:200]
    db_session.expire_all()
    assert db_session.query(MediaAsset).filter(MediaAsset.title == "SvgIcoon").count() == 1
    refused = _upload(
        client,
        ICON_SVG.encode(),
        kind="sponsor",
        name="s.svg",
        ctype="image/svg+xml",
        title="SvgSponsor",
    )
    db_session.expire_all()
    assert db_session.query(MediaAsset).filter(MediaAsset.title == "SvgSponsor").count() == 0, (
        refused.text[:200]
    )


def test_the_kind_is_a_row_of_the_code_list_with_both_words(db_session):
    from sqlalchemy import text

    rows = db_session.execute(
        text(
            "SELECT language, value FROM media.media_kind_labels WHERE code = 'site_icon' ORDER BY language"
        )
    ).all()
    assert [r[0] for r in rows] == ["en", "nl"] and all(r[1] for r in rows)
