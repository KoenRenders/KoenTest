"""Tests voor de chatbot-POC 'Raakje' (#205).

Bewaakt de invarianten die ertoe doen:
- de tool-laag is de security-grens (enkel 3 publieke tools, niets anders);
- idee-indienen hergebruikt exact het IdeaBox-schrijfpad;
- de activiteiten-tool toont enkel komende, niet-geannuleerde activiteiten;
- de HTTP-vangrails (per-bericht cap, geschiedenis, laatste = user) werken;
- de provider is aantoonbaar swapbaar (Mock loopt de volledige tool-loop af).
"""
import json
from datetime import date, timedelta

from app.models.activity import Activity, ActivityDate
from app.models.idea import Idea
from app.domains.chatbot.tools import execute_tool, ALLOWED_TOOLS
from app.domains.chatbot.context import build_system_prompt


# ── Security-grens van de tools ──────────────────────────────────────────────

def _page(db, **kw):
    from app.models.cms import CmsPage
    defaults = {"title": "Pagina", "slug": "p", "content": "inhoud", "is_published": True}
    page = CmsPage(**{**defaults, **kw})
    db.add(page)
    db.flush()
    return page


def test_cms_context_renders_placeholders(db_session):
    """De bot moet de echte waarde zien, niet de ruwe {{code}} (#205)."""
    from app.domains.chatbot.context import build_system_prompt

    _page(db_session, slug="lid", content="Het lidgeld bedraagt {{membership_price_full}} euro.")
    prompt = build_system_prompt(db_session)
    assert "{{membership_price_full}}" not in prompt
    assert "bedraagt 35,00 euro" in prompt  # gerenderd ín de paginatekst


def test_membership_block_always_present(db_session):
    """Het membership-blok injecteert prijzen/tarieven, los van CMS (#205)."""
    from app.domains.chatbot.context import build_system_prompt

    prompt = build_system_prompt(db_session)
    assert "Lidmaatschap" in prompt
    assert "35,00" in prompt and "17,50" in prompt


def test_cms_page_can_be_excluded(db_session):
    """chatbot_info-rij met is_active=false → pagina niet naar de bot (opt-out)."""
    from app.models.chatbot_info import ChatbotInfo
    from app.domains.chatbot.context import build_system_prompt

    page = _page(db_session, slug="geheim", content="GEHEIME PAGINATEKST")
    db_session.add(ChatbotInfo(cms_page_id=page.id, is_active=False))
    db_session.flush()
    assert "GEHEIME PAGINATEKST" not in build_system_prompt(db_session)


def test_cms_override_replaces_content(db_session):
    from app.models.chatbot_info import ChatbotInfo
    from app.domains.chatbot.context import build_system_prompt

    page = _page(db_session, slug="over", content="ORIGINELE INHOUD")
    db_session.add(ChatbotInfo(cms_page_id=page.id, text_override="BOT-SPECIFIEKE TEKST"))
    db_session.flush()
    prompt = build_system_prompt(db_session)
    assert "BOT-SPECIFIEKE TEKST" in prompt
    assert "ORIGINELE INHOUD" not in prompt


def test_free_note_added_to_context(db_session):
    from app.models.chatbot_info import ChatbotInfo
    from app.domains.chatbot.context import build_system_prompt

    db_session.add(ChatbotInfo(title="Praktisch", text_addition="We zijn een KWB-vereniging."))
    db_session.flush()
    assert "We zijn een KWB-vereniging." in build_system_prompt(db_session)


def test_only_three_public_tools_are_allowed():
    assert ALLOWED_TOOLS == {
        "get_activities",
        "get_activity_detail",
        "submit_idea",
    }


def test_execute_tool_rejects_unknown_tool(db_session):
    out = json.loads(execute_tool("delete_all_members", {}, db_session))
    assert "error" in out
    # Geen uitvoering, enkel een nette weigering.
    assert "niet-toegelaten" in out["error"].lower()


# ── submit_idea hergebruikt het IdeaBox-schrijfpad ───────────────────────────

def test_submit_idea_creates_idea_row(db_session, monkeypatch):
    import app.domains.chatbot.tools as tools

    monkeypatch.setattr(tools, "send_idea_acknowledgement", lambda **kw: None)
    before = db_session.query(Idea).count()
    out = json.loads(
        execute_tool(
            "submit_idea",
            {"name": "Jan", "content": "Mooie speeltuin idee", "email": "jan@example.com"},
            db_session,
        )
    )
    assert out["ok"] is True
    after = db_session.query(Idea).count()
    assert after == before + 1
    idea = db_session.query(Idea).order_by(Idea.id.desc()).first()
    assert idea.submitter_name == "Jan"
    assert idea.submitter_email == "jan@example.com"
    assert idea.content == "Mooie speeltuin idee"


def test_submit_idea_requires_email(db_session):
    """Zonder e-mailadres: geweigerd, géén idee weggeschreven (verplicht voor antwoord)."""
    before = db_session.query(Idea).count()
    for args in (
        {"name": "Jan", "content": "Idee zonder mail"},
        {"name": "Jan", "content": "Idee", "email": ""},
        {"name": "", "content": "Idee", "email": "jan@example.com"},
    ):
        out = json.loads(execute_tool("submit_idea", args, db_session))
        assert out["ok"] is False
        assert "error" in out
    assert db_session.query(Idea).count() == before


def test_submit_idea_rejects_invalid_email(db_session):
    before = db_session.query(Idea).count()
    out = json.loads(
        execute_tool(
            "submit_idea",
            {"name": "Jan", "content": "Idee", "email": "geen-mailadres"},
            db_session,
        )
    )
    assert out["ok"] is False
    assert db_session.query(Idea).count() == before


# ── get_activities: komend (default) én verleden (when='past') ───────────────

def _activity(db, name, when, *, cancelled=False):
    a = Activity(name=name, is_cancelled=cancelled)
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=when))
    db.flush()
    return a


def test_upcoming_excludes_past_and_cancelled(db_session):
    future = date.today() + timedelta(days=10)
    past = date.today() - timedelta(days=10)
    _activity(db_session, "Toekomstfeest", future)
    _activity(db_session, "Oud feest", past)
    _activity(db_session, "Afgelast feest", future, cancelled=True)

    # Default (geen when) = komend.
    out = json.loads(execute_tool("get_activities", {}, db_session))
    names = {a["name"] for a in out["activities"]}
    assert out["when"] == "upcoming"
    assert "Toekomstfeest" in names
    assert "Oud feest" not in names
    assert "Afgelast feest" not in names


def test_past_returns_only_past_most_recent_first(db_session):
    today = date.today()
    _activity(db_session, "Toekomstfeest", today + timedelta(days=10))
    _activity(db_session, "Lang geleden", today - timedelta(days=300))
    _activity(db_session, "Recent voorbij", today - timedelta(days=5))
    _activity(db_session, "Afgelast verleden", today - timedelta(days=20), cancelled=True)

    out = json.loads(execute_tool("get_activities", {"when": "past"}, db_session))
    names = [a["name"] for a in out["activities"]]
    assert out["when"] == "past"
    assert "Toekomstfeest" not in names          # geen toekomst
    assert "Afgelast verleden" not in names       # geannuleerd telt niet
    assert names == ["Recent voorbij", "Lang geleden"]  # meest recent eerst


def test_past_respects_limit(db_session):
    today = date.today()
    for i in range(25):
        _activity(db_session, f"Verleden {i}", today - timedelta(days=i + 1))
    out = json.loads(execute_tool("get_activities", {"when": "past"}, db_session))
    assert len(out["activities"]) == 20


# ── System-prompt: temporeel anker (#249) ────────────────────────────────────

def test_system_prompt_includes_today(db_session):
    """De prompt geeft de datum van vandaag mee, zodat het model verleden/toekomst
    kan onderscheiden en geen voorbije datum als 'eerstvolgende' verzint."""
    prompt = build_system_prompt(db_session)
    assert date.today().isoformat() in prompt
    assert "Bereken zelf geen concrete datums" in prompt


# ── Vorm-validatie: cap enkel op bezoeker-berichten (#251) ───────────────────

def test_long_assistant_message_in_history_is_allowed():
    """Een lang bot-antwoord in de geschiedenis mag — anders blokkeert één lang
    antwoord het hele gesprek met een 422."""
    from app.schemas.chat import ChatRequest

    req = ChatRequest(
        messages=[
            {"role": "user", "content": "hoi"},
            {"role": "assistant", "content": "a" * 5000},
            {"role": "user", "content": "en nu?"},
        ]
    )
    assert len(req.messages) == 3


def test_long_user_message_is_rejected():
    import pytest
    from pydantic import ValidationError

    from app.schemas.chat import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest(messages=[{"role": "user", "content": "a" * 5000}])


# ── HTTP-vangrails op /api/v1/chat ───────────────────────────────────────────

def test_message_over_cap_is_rejected_422(client):
    from app.config import settings

    too_long = "a" * (settings.chat_max_input_chars + 1)
    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": too_long}]})
    assert r.status_code == 422


def test_last_message_must_be_user(client):
    r = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "assistant", "content": "hoi"}]},
    )
    assert r.status_code == 422


# ── Provider-swap: Mock loopt de volledige tool-loop af ──────────────────────

def _collect_sse(text: str) -> str:
    parts = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = json.loads(line[5:].strip())
        if payload.get("delta"):
            parts.append(payload["delta"])
    return "".join(parts)


def test_chat_disabled_returns_404(client, monkeypatch):
    """Hoofdschakelaar uit (default) → het endpoint bestaat 'niet'."""
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", False)
    r = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "Hallo"}]},
    )
    assert r.status_code == 404


def test_chat_endpoint_mock_simple_answer(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    r = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "Wie zijn jullie?"}]},
    )
    assert r.status_code == 200
    answer = _collect_sse(r.text)
    assert "Raakje" in answer


def test_chat_endpoint_mock_runs_tool_loop(client, db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    # Een activiteit zodat de tool data heeft.
    _activity(db_session, "Quiz", date.today() + timedelta(days=5))

    r = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "Welke activiteiten zijn er?"}]},
    )
    assert r.status_code == 200
    answer = _collect_sse(r.text)
    # De data-bewuste mock toont de echte opgehaalde activiteit in het antwoord.
    assert "Quiz" in answer
