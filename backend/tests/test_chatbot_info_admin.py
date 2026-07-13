"""Tests voor het admin-beheer van chatbot_info (#235)."""
from app.domains.activities.api import Activity
from app.models.asset import MediaAsset
from app.models.chatbot_info import ChatbotInfo
from app.models.cms import CmsPage


def _poster(db):
    a = Activity(name="Lentewandeling")
    db.add(a)
    db.flush()
    asset = MediaAsset(
        kind="activity_poster", activity_id=a.id,
        data=b"p", content_type="image/png", byte_size=1,
    )
    db.add(asset)
    db.flush()
    return asset


def _page(db):
    page = CmsPage(title="Lid worden", slug="lid-worden", content="tekst", is_published=True)
    db.add(page)
    db.flush()
    return page


# ── Autorisatie ──────────────────────────────────────────────────────────────

def test_list_requires_admin(client):
    r = client.get("/api/v1/admin/chatbot-info")
    assert r.status_code in (401, 403)


# ── Overzicht in drie groepen ────────────────────────────────────────────────

def test_list_returns_groups(client, db_session, admin_headers):
    _poster(db_session)
    _page(db_session)
    db_session.add(ChatbotInfo(title="Praktisch", text_addition="We zijn een KWB-vereniging."))
    db_session.flush()

    r = client.get("/api/v1/admin/chatbot-info", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["documents"]) == 1
    assert body["documents"][0]["label"].startswith("Lentewandeling")
    assert any(p["title"] == "Lid worden" for p in body["cms"])
    assert any(n["title"] == "Praktisch" for n in body["notes"])


# ── Upsert media / cms ───────────────────────────────────────────────────────

def test_upsert_media_creates_override_row(client, db_session, admin_headers):
    asset = _poster(db_session)
    r = client.put(
        f"/api/v1/admin/chatbot-info/media/{asset.id}",
        headers=admin_headers,
        json={"text_override": "Breng laarzen mee.", "is_active": True},
    )
    assert r.status_code == 200
    row = db_session.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset.id).first()
    assert row.text_override == "Breng laarzen mee."


def test_upsert_cms_can_exclude_page(client, db_session, admin_headers):
    page = _page(db_session)
    r = client.put(
        f"/api/v1/admin/chatbot-info/cms/{page.id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert r.status_code == 200
    row = db_session.query(ChatbotInfo).filter(ChatbotInfo.cms_page_id == page.id).first()
    assert row.is_active is False


# ── Notities CRUD ────────────────────────────────────────────────────────────

def test_create_update_delete_note(client, db_session, admin_headers):
    r = client.post(
        "/api/v1/admin/chatbot-info/notes",
        headers=admin_headers,
        json={"title": "Toon", "text_addition": "Antwoord beknopt.", "is_active": True},
    )
    assert r.status_code == 201
    row_id = r.json()["id"]

    r2 = client.patch(
        f"/api/v1/admin/chatbot-info/{row_id}",
        headers=admin_headers,
        json={"title": "Toon", "text_addition": "Antwoord kort en warm.", "is_active": True},
    )
    assert r2.status_code == 200

    r3 = client.delete(f"/api/v1/admin/chatbot-info/{row_id}", headers=admin_headers)
    assert r3.status_code == 204
    assert db_session.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first() is None


# ── 'Opnieuw lezen'-endpoint ─────────────────────────────────────────────────

def test_reextract_endpoint(client, db_session, admin_headers):
    asset = _poster(db_session)
    r = client.post(f"/api/v1/admin/media/{asset.id}/extract", headers=admin_headers)
    assert r.status_code == 202


def test_reextract_unknown_asset_404(client, admin_headers):
    r = client.post("/api/v1/admin/media/999999/extract", headers=admin_headers)
    assert r.status_code == 404
