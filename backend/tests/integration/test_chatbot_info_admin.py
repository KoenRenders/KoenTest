"""Tests voor het admin-beheer van chatbot_info (#235)."""

from app.domains.activities.api import Activity
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.chatbot import info_service
from app.domains.chatbot.models import ChatbotInfo
from app.domains.cms.api import CmsPage
from app.domains.media import extraction
from app.domains.media.api import MediaAsset
from app.domains.media.service import EXTRACT_JOB
from app.kernel.jobs import KernelJob, run_due_jobs
from app.schemas.chatbot_info import ChatbotInfoEdit, NoteCreate
from tests.conftest import SEEDED_ADMIN_EMAIL


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


def _press(client, asset_id: int):
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return client.post(
        f"/admin/ai-context/documenten/{asset_id}/opnieuw-lezen",
        headers={"X-CSRF-Token": csrf_token_for(session)},
    )


def test_the_button_plans_a_forced_reading_and_the_job_replaces_the_text(
    client, db_session, monkeypatch
):
    """The button asks media through the port `ReadTextAgain` (#1251): one job,
    forced, planned in the request's transaction — and when it runs only the
    extracted text is replaced; what the board wrote beside it stays.

    Proven red (9 October 2026): the commit taken out of
    `chatbot.info_service.read_document_again` → no job is found after the
    request, and the text stays the old one."""
    asset = _poster(db_session)
    db_session.add(
        ChatbotInfo(
            media_asset_id=asset.id,
            title=asset.title,
            extracted_text="oude tekst",
            text_addition="door het bestuur toegevoegd",
        )
    )
    db_session.commit()
    monkeypatch.setattr(extraction, "extract_document_text", lambda raw, ct, **_k: "nieuwe tekst")

    answer = _press(client, asset.id)

    assert answer.status_code == 200, answer.text[:200]
    db_session.expire_all()
    jobs = db_session.query(KernelJob).filter(KernelJob.name == EXTRACT_JOB).all()
    assert [job.payload for job in jobs] == [{"asset_id": asset.id, "force": True}]
    run_due_jobs(db_session)
    db_session.expire_all()
    row = db_session.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset.id).one()
    assert (row.extracted_text, row.text_addition) == (
        "nieuwe tekst",
        "door het bestuur toegevoegd",
    )


def test_the_button_on_a_document_that_is_not_there_answers_404(client, db_session):
    answer = _press(client, 999_999)
    assert answer.status_code == 404
    assert db_session.query(KernelJob).filter(KernelJob.name == EXTRACT_JOB).count() == 0


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
