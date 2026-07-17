"""Fase 4c-2 (#404): Raakje (htmx) en het ai-context-scherm."""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.chatbot.models import ChatbotInfo


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_raakje_page_renders(client):
    resp = client.get("/raakje")
    assert resp.status_code == 200 and "Raakje" in resp.text


def test_raakje_vraag_geeft_antwoord_via_mock(client, db_session, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "chat_enabled", True)
    # In tests draait de mock-provider (CHAT_PROVIDER default) — geen netwerk.
    resp = client.post("/raakje/vraag", data={"vraag": "Wat is Raak?"})
    assert resp.status_code == 200 and "Wat is Raak?" in resp.text


def test_raakje_lege_vraag(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "chat_enabled", True)
    resp = client.post("/raakje/vraag", data={"vraag": "  "})
    assert resp.status_code == 200 and "Typ eerst een vraag" in resp.text


def test_ai_context_scherm_en_notitieflow(client, db_session):
    csrf = _login(client)
    page = client.get("/admin/ai-context")
    assert page.status_code == 200 and "Notities" in page.text

    resp = client.post("/admin/ai-context/notities",
                       data={"title": "Parkeren", "text_addition": "Parkeren kan aan de kerk."},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "Parkeren" in resp.text
    note = (db_session.query(ChatbotInfo)
            .filter(ChatbotInfo.title == "Parkeren").one())

    uit = client.post(f"/admin/ai-context/{note.id}/toggle", headers={"X-CSRF-Token": csrf})
    assert uit.status_code == 200
    db_session.expire_all()
    assert note.is_active is False

    weg = client.post(f"/admin/ai-context/{note.id}/verwijderen", headers={"X-CSRF-Token": csrf})
    assert weg.status_code == 200
    assert db_session.query(ChatbotInfo).filter(ChatbotInfo.id == note.id).first() is None


def test_ai_context_requires_session(client):
    assert client.get("/admin/ai-context").status_code == 401


def test_document_toont_gelezen_ocr_tekst(client, db_session):
    """#522: de OCR-/extractie-tekst van een document is read-only zichtbaar in
    admin-raakje, zodat de beheerder ziet wat Raakje uit de affiche/PDF las."""
    from app.domains.media.models import MediaAsset

    asset = MediaAsset(kind="activity_poster", data=b"x", content_type="image/png")
    db_session.add(asset)
    db_session.flush()
    db_session.add(ChatbotInfo(media_asset_id=asset.id, is_active=True,
                              extracted_text="AFFICHE: Zomerbar op 1 juli om 19u"))
    db_session.commit()

    _login(client)
    resp = client.get("/admin/ai-context")
    assert resp.status_code == 200
    assert "Toon gelezen tekst (OCR)" in resp.text
    assert "AFFICHE: Zomerbar op 1 juli om 19u" in resp.text
