"""React-exit 405-e (stap 1): URL-pariteit — fotopagina's, admin-dashboard en
redirects van de oude React-paden."""
import io

from PIL import Image

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, make_session_value


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def test_redirects_oude_paden(client):
    for pad, doel in (("/archief", "/activiteiten/archief"),
                      ("/admin/login", "/aanmelden"),
                      ("/admin/emails", "/admin/e-maillog"),
                      ("/admin/login/verify?token=abc", "/login/verify?token=abc"),
                      ("/leden/login/verify?token=abc", "/login/verify?token=abc")):
        resp = client.get(pad, follow_redirects=False)
        assert resp.status_code == 302, pad
        assert resp.headers["location"] == doel, pad


def test_fotos_paginas(client, db_session):
    from datetime import date, timedelta

    from app.domains.activities.api import Activity, ActivityDate
    from app.domains.media.models import MediaAsset

    gisteren = date.today() - timedelta(days=1)
    act = Activity(name="Dorpsfeest", is_cancelled=False)
    db_session.add(act)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=act.id, start_date=gisteren))
    buf = io.BytesIO()
    Image.new("RGB", (30, 20), (10, 120, 200)).save(buf, format="PNG")
    db_session.add(MediaAsset(kind="activity_photo", activity_id=act.id,
                              is_active=True, data=buf.getvalue(),
                              thumbnail=buf.getvalue(), content_type="image/png",
                              sort_order=0))
    db_session.flush()

    overzicht = client.get("/fotos")
    assert overzicht.status_code == 200 and "Dorpsfeest" in overzicht.text

    album = client.get(f"/activiteiten/{act.id}/fotos")
    assert album.status_code == 200 and "Dorpsfeest" in album.text
    assert "/api/v1/media/" in album.text


def test_admin_dashboard(client):
    assert client.get("/admin").status_code == 401
    _login(client)
    resp = client.get("/admin")
    assert resp.status_code == 200
    for label in ("Dashboard", "Actieve leden", "Komende activiteiten",
                  "Openstaand saldo"):
        assert label in resp.text, label
