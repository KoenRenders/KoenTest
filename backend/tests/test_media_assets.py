"""Tests voor de assetbibliotheek: upload (admin), publiek serveren met caching,
en de sponsor-/foto-endpoints."""

from io import BytesIO

from PIL import Image

from tests import media_door
from tests.conftest import seed_activity_with_product


def _png_bytes(size=(300, 200), color=(10, 120, 200)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def test_sponsor_upload_serve_and_list(client, admin_headers):
    files = {"files": ("logo.png", _png_bytes(), "image/png")}
    resp = media_door.upload(
        client, files, {"kind": "sponsor", "title": "Mona", "link_url": "https://example.org"}
    )
    assert resp.status_code == 200, resp.text
    asset = resp.json()[0]
    assert asset["kind"] == "sponsor"
    assert asset["title"] == "Mona"

    # The library lists it among the sponsors (the JSON list of sponsors went
    # with #1251; the site reads its footer logos itself).
    sponsors = media_door.listing(client, kind="sponsor")
    assert sponsors.status_code == 200
    assert any(s["id"] == asset["id"] for s in sponsors.json())

    # Beeld wordt geserveerd met lange cache + ETag.
    img = client.get(asset["url"])
    assert img.status_code == 200
    assert img.headers["cache-control"].startswith("public, max-age=")
    etag = img.headers["etag"]

    # If-None-Match → 304.
    again = client.get(asset["url"], headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_activity_photo_requires_activity_id(client, admin_headers):
    files = {"files": ("foto.png", _png_bytes(), "image/png")}
    resp = media_door.upload(client, files, {"kind": "activity_photo"})
    assert resp.status_code == 400


def test_activity_photos_listed_per_activity(client, db_session, admin_headers):
    activity, _comp, _product = seed_activity_with_product(db_session)
    files = [
        ("files", ("a.png", _png_bytes(), "image/png")),
        ("files", ("b.png", _png_bytes(color=(200, 30, 30)), "image/png")),
    ]
    resp = media_door.upload(
        client, files, {"kind": "activity_photo", "activity_id": str(activity.id)}
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 2

    photos = media_door.photos(client, activity.id)
    assert photos.status_code == 200
    assert len(photos.json()) == 2
    # Thumbnail-endpoint werkt.
    thumb = client.get(photos.json()[0]["thumb_url"])
    assert thumb.status_code == 200


def test_non_image_rejected(client, admin_headers):
    files = {"files": ("stuk.txt", b"geen afbeelding", "text/plain")}
    resp = media_door.upload(client, files, {"kind": "sponsor"})
    assert resp.status_code == 400
