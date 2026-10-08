"""Poster (activiteit) en info/reglement (onderdeel): upload van afbeelding of PDF,
die primeert op de URL; geen soft delete (#223)."""

from io import BytesIO

from PIL import Image

from app.domains.activities.api import Activity, ActivitySubRegistration
from app.domains.media.api import MediaAsset
from tests import media_door
from tests.conftest import seed_activity_with_product


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (12, 12), "red").save(buf, format="PNG")
    return buf.getvalue()


_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def test_upload_activity_poster_image_primes_over_url(client, db_session, admin_headers):
    activity, _comp, _p = seed_activity_with_product(db_session)
    activity.poster_url = "https://extern/affiche.png"
    db_session.flush()

    resp = media_door.set_poster(
        client, activity.id, {"file": ("affiche.png", _png(), "image/png")}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_pdf"] is False

    db_session.expire_all()
    a = db_session.query(Activity).filter(Activity.id == activity.id).first()
    assert a.poster_asset_url is not None  # upload primeert
    assert a.poster_asset_is_pdf is False
    assert a.poster_url == "https://extern/affiche.png"  # URL blijft als fallback bewaard


def test_upload_activity_poster_pdf(client, db_session, admin_headers):
    activity, _comp, _p = seed_activity_with_product(db_session)
    resp = media_door.set_poster(
        client, activity.id, {"file": ("affiche.pdf", _PDF, "application/pdf")}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_pdf"] is True
    # Wordt als PDF inline geserveerd, met een nette bestandsnaam (#223).
    served = client.get(body["url"])
    assert served.status_code == 200
    assert "application/pdf" in served.headers.get("content-type", "")
    disp = served.headers.get("content-disposition", "")
    assert "inline" in disp and "poster" in disp

    db_session.expire_all()
    a = db_session.query(Activity).filter(Activity.id == activity.id).first()
    assert a.poster_asset_is_pdf is True


def test_replacing_poster_hard_deletes_the_old_one(client, db_session, admin_headers):
    activity, _comp, _p = seed_activity_with_product(db_session)
    media_door.set_poster(client, activity.id, {"file": ("a.png", _png(), "image/png")})
    media_door.set_poster(client, activity.id, {"file": ("b.pdf", _PDF, "application/pdf")})
    db_session.expire_all()
    # Precies één asset (geen soft-delete-ballast): de oude is écht weg.
    assets = (
        db_session.query(MediaAsset)
        .execution_options(include_deleted=True)
        .filter(MediaAsset.kind == "activity_poster", MediaAsset.activity_id == activity.id)
        .all()
    )
    assert len(assets) == 1
    assert assets[0].content_type == "application/pdf"


def test_delete_poster_falls_back_to_url(client, db_session, admin_headers):
    activity, _comp, _p = seed_activity_with_product(db_session)
    media_door.set_poster(client, activity.id, {"file": ("a.png", _png(), "image/png")})
    resp = media_door.drop_poster(client, activity.id)
    assert resp.status_code == 204
    db_session.expire_all()
    a = db_session.query(Activity).filter(Activity.id == activity.id).first()
    assert a.poster_asset_url is None


def test_upload_component_info_pdf(client, db_session, admin_headers):
    _activity, comp, _p = seed_activity_with_product(db_session)
    resp = media_door.set_component_info(
        client, comp.id, {"file": ("zomaar.pdf", _PDF, "application/pdf")}
    )
    assert resp.status_code == 200, resp.text
    # Betekenisvolle bestandsnaam o.b.v. de context, niet de geüploade naam (#223).
    disp = client.get(resp.json()["url"]).headers.get("content-disposition", "")
    assert "info" in disp and "zomaar" not in disp
    db_session.expire_all()
    c = (
        db_session.query(ActivitySubRegistration)
        .filter(ActivitySubRegistration.id == comp.id)
        .first()
    )
    assert c.info_asset_url is not None
    assert c.info_asset_is_pdf is True


def test_unsupported_file_type_rejected(client, db_session, admin_headers):
    activity, _comp, _p = seed_activity_with_product(db_session)
    resp = media_door.set_poster(
        client, activity.id, {"file": ("evil.exe", b"MZ", "application/octet-stream")}
    )
    assert resp.status_code == 400
