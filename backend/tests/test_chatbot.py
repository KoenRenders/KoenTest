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


# ── Security-grens van de tools ──────────────────────────────────────────────

def test_only_three_public_tools_are_allowed():
    assert ALLOWED_TOOLS == {
        "get_upcoming_activities",
        "get_activity_detail",
        "submit_idea",
    }


def test_execute_tool_rejects_unknown_tool(db_session):
    out = json.loads(execute_tool("delete_all_members", {}, db_session))
    assert "error" in out
    # Geen uitvoering, enkel een nette weigering.
    assert "niet-toegelaten" in out["error"].lower()


# ── submit_idea hergebruikt het IdeaBox-schrijfpad ───────────────────────────

def test_submit_idea_creates_idea_row(db_session):
    before = db_session.query(Idea).count()
    out = json.loads(
        execute_tool(
            "submit_idea",
            {"name": "Jan", "content": "Mooie speeltuin idee", "email": None},
            db_session,
        )
    )
    assert out["ok"] is True
    after = db_session.query(Idea).count()
    assert after == before + 1
    idea = db_session.query(Idea).order_by(Idea.id.desc()).first()
    assert idea.submitter_name == "Jan"
    assert idea.content == "Mooie speeltuin idee"


# ── get_upcoming_activities: enkel komend + niet-geannuleerd ─────────────────

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

    out = json.loads(execute_tool("get_upcoming_activities", {}, db_session))
    names = {a["name"] for a in out["activities"]}
    assert "Toekomstfeest" in names
    assert "Oud feest" not in names
    assert "Afgelast feest" not in names


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


def test_chat_endpoint_mock_simple_answer(client, monkeypatch):
    from app.config import settings

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

    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    # Een activiteit zodat de tool data heeft.
    _activity(db_session, "Quiz", date.today() + timedelta(days=5))

    r = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "Welke activiteiten zijn er?"}]},
    )
    assert r.status_code == 200
    answer = _collect_sse(r.text)
    # De mock geeft na een tool-resultaat een herkenbaar eindantwoord.
    assert "mock-provider" in answer.lower()
