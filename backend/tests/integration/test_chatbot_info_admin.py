"""Tests voor het admin-beheer van chatbot_info (#235)."""

from app.domains.activities.api import Activity
from app.domains.chatbot import info_service
from app.domains.chatbot.models import ChatbotInfo
from app.domains.cms.api import CmsPage
from app.domains.media.api import MediaAsset
from app.schemas.chatbot_info import ChatbotInfoEdit, NoteCreate
from tests import media_door


def _poster(db):
    a = Activity(name="Lentewandeling")
    db.add(a)
    db.flush()
    asset = MediaAsset(
        kind="activity_poster",
        activity_id=a.id,
        data=b"p",
        content_type="image/png",
        byte_size=1,
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


# ── Overzicht in drie groepen ────────────────────────────────────────────────


def test_list_returns_groups(db_session):
    _poster(db_session)
    _page(db_session)
    db_session.add(ChatbotInfo(title="Praktisch", text_addition="We zijn een KWB-vereniging."))
    db_session.flush()

    body = info_service.list_chatbot_info(db_session)
    assert len(body["documents"]) == 1
    assert body["documents"][0]["label"].startswith("Lentewandeling")
    assert any(p["title"] == "Lid worden" for p in body["cms"])
    assert any(n["title"] == "Praktisch" for n in body["notes"])


# ── (the two upsert routes went with #1251, see the PR) ───────────────────────────────────────────────────────


# ── Notities CRUD ────────────────────────────────────────────────────────────


def test_create_update_delete_note(db_session):
    """The three functions the screen "Wat Raakje weet" calls (`chatbot.info_service`)."""
    made = info_service.create_note(
        db_session,
        NoteCreate(title="Toon", text_addition="Antwoord beknopt.", is_active=True),
    )
    row_id = made["id"]

    changed = info_service.update_row(
        db_session,
        row_id,
        ChatbotInfoEdit(title="Toon", text_addition="Antwoord kort en warm.", is_active=True),
    )
    assert changed["text_addition"] == "Antwoord kort en warm."

    info_service.delete_row(db_session, row_id)
    assert db_session.query(ChatbotInfo).filter(ChatbotInfo.id == row_id).first() is None


# ── 'Opnieuw lezen'-endpoint ─────────────────────────────────────────────────


def test_reextract_endpoint(client, db_session, admin_headers):
    asset = _poster(db_session)
    r = media_door.reextract(client, asset.id)
    assert r.status_code == 202


def test_reextract_unknown_asset_404(client, admin_headers):
    r = media_door.reextract(client, 999999)
    assert r.status_code == 404


# ── A note has a title and a text: the service's rule (CR-13 phase 4c, #1251) ──


def test_a_note_without_a_title_or_a_text_is_refused_by_the_service(db_session):
    """The rule stood in the screen alone; it holds for every entrance now.

    Proven red (8 October 2026): the check taken out of `info_service.add_note` →
    a note without a title is stored (no refusal raised).
    """
    import pytest

    before = db_session.query(ChatbotInfo).count()
    for title, text in (("", "Antwoord beknopt."), ("Toon", "   "), ("  ", "")):
        with pytest.raises(info_service.InfoRefused, match="Titel en tekst zijn verplicht"):
            info_service.add_note(db_session, title=title, text=text)
    assert db_session.query(ChatbotInfo).count() == before

    made = info_service.add_note(db_session, title="  Toon ", text=" Antwoord beknopt. ")
    assert (made["title"], made["text_addition"]) == ("Toon", "Antwoord beknopt.")


def test_the_screen_shows_the_services_refusal_in_the_same_words(client, db_session):
    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    answer = client.post(
        "/admin/ai-context/notities",
        data={"title": "Toon", "text_addition": ""},
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )
    assert answer.status_code == 400
    assert answer.json()["detail"] == "Titel en tekst zijn verplicht."
