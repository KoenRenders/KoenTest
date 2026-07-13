"""React-exit 405-d: server-rendered admin-schermen — pagina's (CMS),
gebruikers, media, wijzigingen en systeeminfo."""
import io

from PIL import Image

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.auth.models import User
from app.domains.cms.models import CmsPage
from app.domains.media.models import MediaAsset


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_schermen_vereisen_sessie(client):
    for pad in ("/admin/paginas", "/admin/gebruikers", "/admin/media",
                "/admin/ledenwijzigingen", "/admin/info"):
        assert client.get(pad).status_code == 401, pad


def test_paginas_crud(client, db_session):
    csrf = _login(client)
    resp = client.post("/admin/paginas", data={"title": "Over ons", "slug": "over-ons"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "Over ons" in resp.text
    page = db_session.query(CmsPage).filter(CmsPage.slug == "over-ons").one()

    detail = client.get(f"/admin/paginas/{page.id}")
    assert detail.status_code == 200 and "Beschikbare placeholders" in detail.text

    resp = client.post(f"/admin/paginas/{page.id}", data={
        "title": "Over ons", "slug": "over-ons", "content": "Welkom bij Raak!",
        "is_published": "1", "sort_order": "5"}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    db_session.expire_all()
    assert page.content == "Welkom bij Raak!"
    assert page.is_published is True and page.show_in_nav is False
    assert page.sort_order == 5

    resp = client.post(f"/admin/paginas/{page.id}/verwijderen",
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert db_session.query(CmsPage).filter(CmsPage.slug == "over-ons").first() is None


def test_gebruikers_beheer(client, db_session):
    csrf = _login(client)
    resp = client.post("/admin/gebruikers", data={"email": "nieuw@example.com"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "nieuw@example.com" in resp.text
    user = db_session.query(User).filter(User.email == "nieuw@example.com").one()

    # dubbel aanmaken → foutbanner, geen crash
    resp = client.post("/admin/gebruikers", data={"email": "nieuw@example.com"},
                       headers={"X-CSRF-Token": csrf})
    assert "al in gebruik" in resp.text

    # deactiveren (checkbox niet meegestuurd = uit)
    resp = client.post(f"/admin/gebruikers/{user.id}", data={},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    db_session.expire_all()
    assert user.is_active is False

    # jezelf verwijderen is geblokkeerd
    zelf = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    resp = client.post(f"/admin/gebruikers/{zelf.id}/verwijderen",
                       headers={"X-CSRF-Token": csrf})
    assert "jezelf niet verwijderen" in resp.text

    resp = client.post(f"/admin/gebruikers/{user.id}/verwijderen",
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 50, 50)).save(buf, format="PNG")
    return buf.getvalue()


def test_media_upload_en_beheer(client, db_session):
    csrf = _login(client)
    resp = client.post("/admin/media",
                       files={"files": ("logo.png", _png_bytes(), "image/png")},
                       data={"kind": "sponsor", "title": "Sponsor X",
                             "link_url": "https://example.com"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "Sponsor X" in resp.text
    asset = db_session.query(MediaAsset).filter(MediaAsset.title == "Sponsor X").one()

    resp = client.post(f"/admin/media/{asset.id}", data={
        "kind": "sponsor", "title": "Sponsor Y", "sort_order": "3", "is_active": "1"},
        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    db_session.expire_all()
    assert asset.title == "Sponsor Y" and asset.sort_order == 3

    resp = client.post(f"/admin/media/{asset.id}/verwijderen", data={"kind": "sponsor"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert db_session.query(MediaAsset).filter(MediaAsset.id == asset.id).first() is None


def test_ledenwijzigingen_en_info(client):
    _login(client)
    resp = client.get("/admin/ledenwijzigingen")
    assert resp.status_code == 200 and "audit-feed" in resp.text

    export = client.get("/admin/ledenwijzigingen/export?since=2026-01-01")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith(
        "application/vnd.oasis.opendocument.spreadsheet")

    info = client.get("/admin/info")
    assert info.status_code == 200 and "Systeeminfo" in info.text
    assert "Mollie-modus" in info.text
