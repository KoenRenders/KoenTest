"""Two media kinds for the Design Studio (#1005, CR-10 §3.11).

`design_image` is the picture that goes into a poster and may be 4096 px instead
of 1600 — an A3 poster needs it. **It is still re-encoded**, and that is the
point of this file: the re-encoding is the security, not the shrinking. It
strips EXIF and the colour profile, reads the type from the CONTENT, and refuses
a file that only claims to be an image.

The exemption hangs on the KIND, not on the size: an activity photo of the same
5000 px source still comes back at 1600.

`design_render` is produced by the studio itself and is refused by the upload.

Broken to see them red (measured):
- `MAX_FULL_BY_KIND` ignored in `process_image` → the design image comes back at
  1600 and the two-kinds test fails;
- the kind passed as "" from `upload_media` → the same test fails through the
  route, which is where the limit is actually used;
- the `design_render` refusal removed → the render is stored;
- `exif=`/`icc_profile=` passed along in the JPEG save → the EXIF test fails;
- the same in the PNG save → the transparent-image test fails. Two tests,
  because `_encode` has two `save()` calls and one test only walks one of them
  (measured: breaking the PNG branch left the JPEG test green).
"""
from io import BytesIO

import pytest
from PIL import Image

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.media.api import MediaAsset
from app.domains.media.images import MAX_FULL, MAX_FULL_BY_KIND, ImageError, process_image
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

GROOT = 5000


def _jpeg(px=GROOT, *, exif=None, icc=None) -> bytes:
    buf = BytesIO()
    img = Image.new("RGB", (px, px // 2), (10, 80, 160))
    extra = {}
    if exif is not None:
        extra["exif"] = exif
    if icc is not None:
        extra["icc_profile"] = icc
    img.save(buf, format="JPEG", quality=70, **extra)
    return buf.getvalue()


def _png(px=40) -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (px, px), (0, 93, 41, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _upload(client, csrf, kind, bytes_, naam="beeld.jpg", type_="image/jpeg",
            titel=None, **extra):
    data = {"kind": kind, "title": titel or f"proef-{kind}"}
    data.update(extra)
    return client.post("/admin/media", files={"files": (naam, bytes_, type_)},
                       data=data, headers={"X-CSRF-Token": csrf})


def _asset(db, titel):
    db.expire_all()
    return db.query(MediaAsset).filter(MediaAsset.title == titel).one_or_none()


# ── De grens hangt aan de soort ──────────────────────────────────────────────

def test_the_same_source_gives_4096_as_design_and_1600_as_photo():
    bron = _jpeg()

    ontwerp = process_image(bron, kind="design_image")
    foto = process_image(bron, kind="activity_photo")

    assert max(ontwerp["width"], ontwerp["height"]) == MAX_FULL_BY_KIND["design_image"]
    assert max(foto["width"], foto["height"]) == MAX_FULL
    assert MAX_FULL_BY_KIND["design_image"] == 4096


def test_an_unknown_kind_keeps_the_ordinary_limit():
    """De uitzondering is een lijst, geen 'grote bestanden mogen groter'."""
    gewoon = process_image(_jpeg(), kind="")
    assert max(gewoon["width"], gewoon["height"]) == MAX_FULL


def test_the_route_passes_the_kind_along(client, db_session):
    """Via de route, want daar wordt de grens echt gebruikt."""
    csrf = _login(client)

    assert _upload(client, csrf, "design_image", _jpeg(),
                   titel="ontwerp-groot").status_code == 204
    assert _upload(client, csrf, "activity_photo", _jpeg(), titel="foto-groot",
                   activity_id="").status_code in (200, 204)

    ontwerp = _asset(db_session, "ontwerp-groot")
    assert max(ontwerp.width, ontwerp.height) == 4096


# ── De hercodering blijft, en die is de beveiliging ──────────────────────────

def test_a_design_image_loses_its_exif_and_colour_profile():
    exif = Image.Exif()
    exif[0x010F] = "Camera van de fotograaf"      # Make
    exif[0x9286] = "Geheime opmerking"            # UserComment
    icc = b"\x00\x00\x02\x0cADBE" + b"\x00" * 100  # genoeg om terug te vinden

    bron = _jpeg(px=2000, exif=exif.tobytes(), icc=icc)
    with Image.open(BytesIO(bron)) as origineel:
        assert origineel.info.get("exif"), "de bron droeg geen EXIF; test bewijst niets"
        assert origineel.info.get("icc_profile"), "de bron droeg geen profiel"

    verwerkt = process_image(bron, kind="design_image")

    with Image.open(BytesIO(verwerkt["data"])) as uit:
        assert not uit.info.get("exif"), "EXIF bleef staan in het design-beeld"
        assert not uit.info.get("icc_profile"), "het kleurprofiel bleef staan"
    assert b"Geheime opmerking" not in verwerkt["data"]


def test_a_transparent_design_image_loses_its_profile_too():
    """The PNG branch keeps transparency and writes no profile (#1005).

    Its own test, because the JPEG test above never touches this branch: a
    sponsor logo and a design with transparency go through `_encode` with
    `keep_alpha`, and that is a second `save()` call.
    """
    icc = b"\x00\x00\x02\x0cADBE" + b"\x00" * 100
    exif = Image.Exif()
    exif[0x9286] = "Geheime opmerking in een png"
    buf = BytesIO()
    Image.new("RGBA", (2000, 1000), (0, 93, 41, 200)).save(
        buf, format="PNG", icc_profile=icc, exif=exif.tobytes())
    bron = buf.getvalue()
    with Image.open(BytesIO(bron)) as origineel:
        assert origineel.info.get("icc_profile"), "de bron droeg geen profiel"
        assert origineel.info.get("exif"), "de bron droeg geen EXIF"

    verwerkt = process_image(bron, kind="design_image")

    assert verwerkt["content_type"] == "image/png", "transparantie ging verloren"
    with Image.open(BytesIO(verwerkt["data"])) as uit:
        assert not uit.info.get("icc_profile"), "het kleurprofiel bleef staan"
        assert not uit.info.get("exif"), "EXIF bleef staan in het png-beeld"
        assert uit.mode == "RGBA"
    assert b"Geheime opmerking" not in verwerkt["data"]


def test_the_type_comes_from_the_content_and_not_from_the_name(client, db_session):
    csrf = _login(client)

    # PNG-bytes onder een .jpg-naam: Pillow leest de inhoud, en de uitvoer is
    # wat de inhoud toelaat (transparantie → PNG).
    resp = _upload(client, csrf, "design_image", _png(), naam="zogezegd.jpg",
                   titel="inhoud-wint")
    assert resp.status_code == 204
    assert _asset(db_session, "inhoud-wint").content_type == "image/png"


def test_html_that_claims_to_be_an_image_is_refused(client, db_session):
    csrf = _login(client)
    rommel = b"<html><body><script>alert(1)</script></body></html>"

    with pytest.raises(ImageError):
        process_image(rommel, kind="design_image")

    resp = _upload(client, csrf, "design_image", rommel, naam="doe-alsof.jpg",
                   titel="geen-beeld")
    assert resp.status_code == 200, "de upload hoort geweigerd te worden"
    assert _asset(db_session, "geen-beeld") is None


def test_a_design_image_keeps_its_thumbnail():
    verwerkt = process_image(_jpeg(px=3000), kind="design_image")
    with Image.open(BytesIO(verwerkt["thumbnail"])) as thumb:
        assert max(thumb.size) == 400


# ── design_render komt niet via een upload ───────────────────────────────────

def test_a_render_cannot_be_uploaded(client, db_session):
    csrf = _login(client)

    resp = _upload(client, csrf, "design_render", _jpeg(px=400), titel="render")

    assert resp.status_code == 200
    assert "Design Studio" in resp.text, "de melding zegt niet waarom"
    assert _asset(db_session, "render") is None


def test_the_upload_kinds_are_exactly_what_may_come_in():
    from app.domains.media.api import (DESIGN_IMAGE_KIND, DESIGN_RENDER_KIND,
                                       UPLOADABLE_KINDS, VALID_KINDS)

    assert DESIGN_IMAGE_KIND in UPLOADABLE_KINDS
    assert DESIGN_RENDER_KIND not in UPLOADABLE_KINDS
    assert UPLOADABLE_KINDS == VALID_KINDS | {DESIGN_IMAGE_KIND}
    assert DESIGN_IMAGE_KIND not in VALID_KINDS, (
        "een design-beeld hoort bij zijn activiteit, niet in de mediabibliotheek")


def test_a_design_image_may_hang_on_an_activity(client, db_session):
    from app.domains.activities.api import Activity

    activiteit = Activity(name="Affiche-activiteit")
    db_session.add(activiteit)
    db_session.flush()
    csrf = _login(client)

    resp = _upload(client, csrf, "design_image", _jpeg(px=800), titel="bij-activiteit",
                   activity_id=str(activiteit.id))

    assert resp.status_code == 204
    assert _asset(db_session, "bij-activiteit").activity_id == activiteit.id
