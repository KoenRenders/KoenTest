"""An SVG as the association logo (#989): cleaned, served safely, PNG for e-mail.

Every test that is about a dangerous construct reads the STORED bytes, not the
message on the screen: a refusal banner says nothing about what reached the
database.

Broken to see them red (measured):
- `_clean` and `_clean_attributes` in `media/svg.py` turned into no-ops (the
  allowlist gone) → the script, onload, foreignObject, external-reference and
  style tests fail on the stored bytes;
- the two SVG headers removed from `_serve` → the header test fails;
- the SVG branch in `newsletter._logo_url` removed → the newsletter test fails
  on a letter that points at the SVG;
- the `kind != "tenant_logo"` refusal removed → the sponsor test fails.
"""
from io import BytesIO

import pytest
from PIL import Image

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.media import svg as svg_mod
from app.domains.media.models import MediaAsset
from app.domains.newsletter import service as nb
from app.domains.newsletter.models import Audience, SubscriberStatus, Subscriber
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.newsletter.api import ReplyToMode

pytestmark = pytest.mark.ui_serverrendered

SVG = "http://www.w3.org/2000/svg"
LOGO = (f'<svg xmlns="{SVG}" viewBox="0 0 120 40">'
        '<defs><linearGradient id="g"><stop offset="0" stop-color="#0051a4"/></linearGradient></defs>'
        '<rect width="120" height="40" fill="url(#g)"/>'
        '<text x="10" y="28" font-size="20">RaaK</text></svg>')


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _upload(client, body, *, kind="tenant_logo", name="logo.svg",
            content_type="image/svg+xml", title="Logo 989"):
    csrf = _login(client)
    data = body.encode() if isinstance(body, str) else body
    return client.post("/admin/media", files={"files": (name, data, content_type)},
                       data={"kind": kind, "title": title},
                       headers={"X-CSRF-Token": csrf})


def _stored(db, title="Logo 989"):
    db.expire_all()
    return db.query(MediaAsset).filter(MediaAsset.title == title).one_or_none()


def _png(width=40, height=30):
    buf = BytesIO()
    Image.new("RGBA", (width, height), (0, 81, 164, 255)).save(buf, format="PNG")
    return buf.getvalue()


# ── A clean logo goes through, with a PNG next to it ─────────────────────────

def test_a_clean_svg_logo_is_stored_as_svg_with_a_png(client, db_session):
    resp = _upload(client, LOGO)
    assert resp.status_code == 204, resp.text

    asset = _stored(db_session)
    assert asset.content_type == "image/svg+xml"
    assert b"<rect" in asset.data and b"RaaK" in asset.data
    assert b"url(#g)" in asset.data, "a local gradient reference is part of a logo"
    assert (asset.width, asset.height) == (120, 40)
    assert asset.thumb_content_type == "image/png"
    with Image.open(BytesIO(asset.thumbnail)) as png:
        assert png.format == "PNG"
        assert png.size == (svg_mod.PNG_MAX_SIDE, 267), "longest side 800, ratio 3:1 kept"


# ── Dangerous constructs never reach the database ────────────────────────────

GEVAARLIJK = {
    "script": f'<svg xmlns="{SVG}" viewBox="0 0 10 10"><script>alert(1)</script>'
              '<rect width="10" height="10"/></svg>',
    "onload": f'<svg xmlns="{SVG}" viewBox="0 0 10 10" onload="alert(1)">'
              '<rect width="10" height="10" onclick="alert(2)"/></svg>',
    "foreignObject": f'<svg xmlns="{SVG}" viewBox="0 0 10 10"><foreignObject>'
                     '<body xmlns="http://www.w3.org/1999/xhtml"><script>alert(1)</script>'
                     '</body></foreignObject><rect width="10" height="10"/></svg>',
    "external": f'<svg xmlns="{SVG}" xmlns:xlink="http://www.w3.org/1999/xlink" '
                'viewBox="0 0 10 10"><use xlink:href="https://evil.example/x.svg#a"/>'
                '<use href="javascript:alert(1)"/><rect width="10" height="10"/></svg>',
    "style": f'<svg xmlns="{SVG}" viewBox="0 0 10 10">'
             '<style>@import url(https://evil.example/x.css);</style>'
             '<rect width="10" height="10" style="fill:url(https://evil.example/p)"/></svg>',
}
VERBODEN = [b"script", b"alert", b"onload", b"onclick", b"foreignObject",
            b"evil.example", b"javascript:", b"@import"]


@pytest.mark.parametrize("soort", sorted(GEVAARLIJK))
def test_a_dangerous_construct_is_not_stored(client, db_session, soort):
    resp = _upload(client, GEVAARLIJK[soort])
    assert resp.status_code == 204, resp.text

    asset = _stored(db_session)
    assert asset is not None
    gevonden = [v for v in VERBODEN if v in asset.data]
    assert not gevonden, (soort, gevonden, asset.data)
    assert b"<rect" in asset.data, "the harmless part stays"


@pytest.mark.parametrize("inhoud,reden", [
    ('<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa">'
     '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
     f'<svg xmlns="{SVG}" viewBox="0 0 1 1"><text>&b;</text></svg>', "entities"),
    ('<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
     f'<svg xmlns="{SVG}" viewBox="0 0 1 1"><text>&x;</text></svg>', "external entity"),
    ('<html><body>geen svg</body></html>', "not an svg"),
    (f'<svg xmlns="{SVG}"><rect width="1" height="1"/></svg>', "no size"),
    ("<svg", "broken"),
])
def test_an_svg_that_cannot_be_trusted_is_refused(client, db_session, inhoud, reden):
    resp = _upload(client, inhoud)
    assert resp.status_code == 200, reden
    assert "logo.svg" in resp.text, reden
    assert _stored(db_session) is None, reden


def test_a_raster_posing_as_svg_is_refused(client, db_session):
    resp = _upload(client, _png())
    assert resp.status_code == 200
    assert _stored(db_session) is None


# ── Only for the logo ────────────────────────────────────────────────────────

def test_an_svg_as_sponsor_logo_is_still_refused(client, db_session):
    resp = _upload(client, LOGO, kind="sponsor")
    assert resp.status_code == 200
    assert "alleen als logo van de vereniging" in resp.text
    assert _stored(db_session) is None


def test_a_png_logo_works_as_before(client, db_session):
    resp = _upload(client, _png(), name="logo.png", content_type="image/png")
    assert resp.status_code == 204
    asset = _stored(db_session)
    assert asset.content_type == "image/png"
    assert asset.thumb_content_type == "image/png"


# ── Served safely ────────────────────────────────────────────────────────────

def test_an_svg_answer_carries_a_csp_and_nosniff(client, db_session):
    _upload(client, LOGO)
    asset = _stored(db_session)

    resp = client.get(f"/api/v1/media/{asset.id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    assert resp.headers.get("content-security-policy") == (
        "default-src 'none'; style-src 'unsafe-inline'")
    assert resp.headers.get("x-content-type-options") == "nosniff"

    thumb = client.get(f"/api/v1/media/{asset.id}/thumb")
    assert thumb.headers["content-type"] == "image/png"


# ── E-mail gets the PNG ──────────────────────────────────────────────────────

def test_a_sent_newsletter_shows_the_png_and_not_the_svg(client, db_session, monkeypatch):
    _upload(client, LOGO)
    asset = _stored(db_session)

    sent = []
    monkeypatch.setattr("app.domains.mail.api.send_campaign_mail",
                        lambda to, subject, body, **_k: sent.append(body) or "sent")
    db_session.add(Subscriber(email="lezer@example.org", status=SubscriberStatus.CONFIRMED,
                              source="admin", unsubscribe_token="tok-989"))
    db_session.flush()
    letter = nb.create_newsletter(db_session, created_by="secretaris@example.org")
    nb.update_draft(db_session, letter, subject="Najaar", body_html="<div>Hallo</div>",
                    audience=Audience.NON_MEMBERS)
    nb.start_sending(db_session, letter, sent_by="secretaris@example.org",
                     reply_to_mode=ReplyToMode.ASSOCIATION, base_url="https://raak.example")
    for _ in range(5):
        if nb.send_batch(db_session, letter.id) in ("done", "paused", "nothing"):
            break

    assert len(sent) == 1
    assert f'src="https://raak.example/api/v1/media/{asset.id}/thumb"' in sent[0]
    assert f'/api/v1/media/{asset.id}"' not in sent[0]


# ── The site and the PDF keep the SVG ────────────────────────────────────────

def test_the_site_and_the_meeting_pdf_use_the_svg_itself(client, db_session):
    """Only e-mail needs the PNG. WeasyPrint draws SVG, so the PDF gets the
    vector — measured by the PDF growing once the logo is there."""
    from datetime import date

    from app.domains.meetings.api import create_meeting

    _login(client)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    zonder = client.get(f"/admin/vergaderingen/{meeting.id}/pdf")
    assert zonder.status_code == 200

    _upload(client, LOGO)
    asset = _stored(db_session)
    assert f'src="/api/v1/media/{asset.id}"' in client.get("/").text

    met = client.get(f"/admin/vergaderingen/{meeting.id}/pdf")
    assert met.status_code == 200 and met.content.startswith(b"%PDF-")
    assert len(met.content) != len(zonder.content), "the logo did not reach the PDF"
