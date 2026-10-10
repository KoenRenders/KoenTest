"""Tests voor de chatbot-POC 'Raakje' (#205).

Bewaakt de invarianten die ertoe doen:
- de tool-laag is de security-grens (enkel 3 publieke tools, niets anders);
- idee-indienen hergebruikt exact het berichten-schrijfpad (#398);
- de activiteiten-tool toont enkel komende, niet-geannuleerde activiteiten;
- de HTTP-vangrails (per-bericht cap, geschiedenis, laatste = user) werken;
- de provider is aantoonbaar swapbaar (Mock loopt de volledige tool-loop af).
"""

import json
from datetime import date, timedelta

from app.domains.activities.api import Activity, ActivityDate
from app.domains.chatbot.context import build_system_prompt
from app.domains.chatbot.tools import ALLOWED_TOOLS, execute_tool
from app.domains.forms.models import FormSubmission

# ── Security-grens van de tools ──────────────────────────────────────────────


def _page(db, **kw):
    from app.domains.cms.api import CmsPage

    defaults = {"title": "Pagina", "slug": "p", "content": "inhoud", "is_published": True}
    page = CmsPage(**{**defaults, **kw})
    db.add(page)
    db.flush()
    return page


def test_cms_context_renders_placeholders(db_session):
    """De bot moet de echte waarde zien, niet de ruwe {{code}} (#205)."""
    from app.domains.chatbot.context import build_system_prompt

    _page(db_session, slug="lid", content="Het lidgeld bedraagt {{membership_price_full}}.")
    prompt = build_system_prompt(db_session)
    assert "{{membership_price_full}}" not in prompt
    # De placeholder levert het volledige bedrag mét euroteken (#579).
    assert "bedraagt €35,00" in prompt  # gerenderd ín de paginatekst


def test_membership_block_always_present(db_session):
    """Het membership-blok injecteert prijzen/tarieven, los van CMS (#205)."""
    from app.domains.chatbot.context import build_system_prompt

    prompt = build_system_prompt(db_session)
    assert "Lidmaatschap" in prompt
    assert "35,00" in prompt and "17,50" in prompt


def test_person_role_guardrail_present(db_session):
    """De persona moet de personen-/rolvangrail bevatten (#309): rollen alleen als
    ze expliciet vermeld staan, nooit afleiden of gegevens van verschillende
    personen (zelfde achternaam) combineren. Voorkomt dat de verwarring tussen twee
    bestuursleden met dezelfde achternaam stilletjes terugkeert door een prompt-edit."""
    from app.domains.chatbot.context import build_system_prompt

    prompt = build_system_prompt(db_session)
    assert "PERSONEN EN HUN ROL" in prompt
    assert "Combineer NOOIT gegevens van verschillende personen" in prompt
    assert "Leid een rol nooit af" in prompt


def _fixed_date(y, m, d):
    import datetime as _dt

    class _D(_dt.date):
        @classmethod
        def today(cls):
            return cls(y, m, d)

    return _D


def test_membership_duration_until_dec31_in_halfprice_window(monkeypatch):
    """Regressie (#273): wie in de halfprijs-periode lid wordt, krijgt de DUUR
    t/m 31 december gecommuniceerd — niet de halfprijs-einddatum (16 sep)."""
    from app.domains.chatbot import context

    monkeypatch.setattr(context, "date", _fixed_date(2026, 7, 1))
    block = context._membership_block()
    assert "lid t/m 31 december 2026" in block
    assert "bepaalt ALLEEN de prijs" in block
    # 16 september mag nergens als lidmaatschap-einddatum staan (wel als prijsgrens).
    assert "lid t/m 16 september" not in block


def test_membership_duration_next_year_after_cutoff(monkeypatch):
    """Wie betaalt vanaf membership_next_year_from_md is gedekt t/m 31 december
    van het volgende jaar (#273)."""
    from app.config import settings
    from app.domains.chatbot import context

    m, d = (int(x) for x in settings.membership_next_year_from_md.split("-"))
    monkeypatch.setattr(context, "date", _fixed_date(2026, m, d))
    block = context._membership_block()
    assert "lid t/m 31 december 2027" in block


def test_cms_page_can_be_excluded(db_session):
    """chatbot_info-rij met is_active=false → pagina niet naar de bot (opt-out)."""
    from app.domains.chatbot.context import build_system_prompt
    from app.domains.chatbot.models import ChatbotInfo

    page = _page(db_session, slug="geheim", content="GEHEIME PAGINATEKST")
    db_session.add(ChatbotInfo(cms_page_id=page.id, is_active=False))
    db_session.flush()
    assert "GEHEIME PAGINATEKST" not in build_system_prompt(db_session)


def test_cms_override_replaces_content(db_session):
    from app.domains.chatbot.context import build_system_prompt
    from app.domains.chatbot.models import ChatbotInfo

    page = _page(db_session, slug="over", content="ORIGINELE INHOUD")
    db_session.add(ChatbotInfo(cms_page_id=page.id, text_override="BOT-SPECIFIEKE TEKST"))
    db_session.flush()
    prompt = build_system_prompt(db_session)
    assert "BOT-SPECIFIEKE TEKST" in prompt
    assert "ORIGINELE INHOUD" not in prompt


def test_free_note_added_to_context(db_session):
    from app.domains.chatbot.context import build_system_prompt
    from app.domains.chatbot.models import ChatbotInfo

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


# ── submit_idea hergebruikt het berichten-schrijfpad (#398) ─────────────────


def test_submit_idea_creates_bericht_submission(db_session):
    from app.domains.workflow.models import WorkflowTask

    before = db_session.query(FormSubmission).count()
    out = json.loads(
        execute_tool(
            "submit_idea",
            {"name": "Jan", "content": "Mooie speeltuin idee", "email": "jan@example.com"},
            db_session,
        )
    )
    db_session.commit()  # the chat's door commits; forms' port does not (#1251)
    assert out["ok"] is True
    assert db_session.query(FormSubmission).count() == before + 1
    sub = db_session.query(FormSubmission).order_by(FormSubmission.id.desc()).first()
    assert sub.submitter_name == "Jan"
    assert sub.submitter_email == "jan@example.com"
    assert sub.answers[0].value_text == "Mooie speeltuin idee"
    # En de behartigen-taak staat open (werkbank, #398).
    task = db_session.query(WorkflowTask).order_by(WorkflowTask.id.desc()).first()
    # #704: `subject_id` is tekst — een onderwerp-id is een ondoorzichtige sleutel
    # en hoort niet te weten of de bron een reeksnummer of een UUID gebruikt.
    assert task.kind == "bericht.behartigen" and task.subject_id == str(sub.id)


def test_submit_idea_requires_email(db_session):
    """Zonder e-mailadres: geweigerd, géén bericht weggeschreven (verplicht voor antwoord)."""
    before = db_session.query(FormSubmission).count()
    for args in (
        {"name": "Jan", "content": "Idee zonder mail"},
        {"name": "Jan", "content": "Idee", "email": ""},
        {"name": "", "content": "Idee", "email": "jan@example.com"},
    ):
        out = json.loads(execute_tool("submit_idea", args, db_session))
        assert out["ok"] is False
        assert "error" in out
    assert db_session.query(FormSubmission).count() == before


def test_submit_idea_rejects_invalid_email(db_session):
    before = db_session.query(FormSubmission).count()
    out = json.loads(
        execute_tool(
            "submit_idea",
            {"name": "Jan", "content": "Idee", "email": "geen-mailadres"},
            db_session,
        )
    )
    assert out["ok"] is False
    assert db_session.query(FormSubmission).count() == before


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
    assert "Toekomstfeest" not in names  # geen toekomst
    assert "Afgelast verleden" not in names  # geannuleerd telt niet
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


def test_submit_idea_lands_in_werkbank(db_session):
    """#398 (verving #260): de bestuursmail is vervangen door een open
    behartigen-taak in de werkbank — dáár blijft niets onopgemerkt."""
    from app.domains.workflow.models import WorkflowTask

    before = db_session.query(WorkflowTask).filter(WorkflowTask.status == "open").count()
    out = json.loads(
        execute_tool(
            "submit_idea",
            {"name": "Jan", "content": "Test idee", "email": "jan@example.com"},
            db_session,
        )
    )
    db_session.commit()  # the chat's door commits; forms' port does not (#1251)
    assert out["ok"] is True
    open_after = db_session.query(WorkflowTask).filter(WorkflowTask.status == "open").count()
    assert open_after == before + 1


# ── Anti-hallucinatie (lagen 1–4) ────────────────────────────────────────────


def test_activity_detail_marks_empty_fields_as_unspecified(db_session):
    """Laag 2: lege velden komen expliciet als 'niet vermeld' terug, zodat de bot
    de afwezigheid als feit ziet i.p.v. te verzinnen."""
    a = _activity(db_session, "Kale activiteit", date.today() + timedelta(days=5))
    out = json.loads(execute_tool("get_activity_detail", {"activity_id": a.id}, db_session))
    # #1028: hier stond `notes`. Die kolom is weg — ze heette intern en ging
    # tegelijk integraal naar het model. De publieke omschrijving nam haar plaats
    # in het antwoord in.
    assert out["description"] == "niet vermeld"
    assert out["flyer_text"] == "niet vermeld"


def test_system_prompt_has_strict_grounding_rules(db_session):
    """Lagen 1 & 4: de prompt verplicht tool-gebruik en verbiedt verzinnen."""
    prompt = build_system_prompt(db_session)
    assert "STRIKTE REGELS" in prompt
    assert "Verzin geen activiteiten" in prompt
    assert "winnen altijd" in prompt  # tool-data wint van vrije tekst


def test_activity_question_forces_a_tool_call():
    """Laag 3: bij een activiteiten-/agendavraag wordt in ronde 1 een tool-aanroep
    geforceerd (tool_choice='any'); een begroeting niet.

    Via `run_public_chat` sinds CR-07: de lus eronder is domeinvrij geworden en
    kent geen agenda's meer, dus de heuristiek zit in de publieke ingang. Het
    gedrag dat deze test bewaakt is niet verhuisd, de plek waar het vandaan komt
    wel."""
    from app.domains.chatbot.providers.base import AssistantMessage
    from app.domains.chatbot.service import _wants_activity_data, run_public_chat

    assert _wants_activity_data([{"role": "user", "content": "Wat staat er op de agenda?"}])
    assert not _wants_activity_data([{"role": "user", "content": "hallo"}])

    seen: dict = {}

    class FakeProvider:
        def __init__(self, key):
            self.key = key

        def complete(self, messages, tools=None, tool_choice=None):
            seen[self.key] = tool_choice
            return AssistantMessage(content="ok")

    run_public_chat(
        None,
        [{"role": "user", "content": "Wat staat er op de agenda?"}],
        FakeProvider("activiteit"),
    )
    run_public_chat(None, [{"role": "user", "content": "hallo"}], FakeProvider("begroeting"))
    assert seen["activiteit"] == "any"
    assert seen["begroeting"] is None


# ── The guards at the visitor's door, /raakje/vraag ───────────────────────────────────────────


def test_a_question_over_the_cap_is_refused_before_the_provider_and_the_budget(client, monkeypatch):
    """One question has a length, at the door a visitor uses (#1251). The cap
    stood at the JSON route alone; the screen route took a question of any
    length, bounded only by what was left of the day's budget.

    Refused in the panel with the sentence that names the number, the question
    kept in the field, nothing sent to the provider, nothing charged.

    Proven red (8 October 2026): the check taken out of `raakje_vraag` → the
    provider is called ("the provider was asked") and the answer is shown.
    """
    from app.config import settings
    from app.domains.chatbot import service
    from app.domains.chatbot.limits import chat_char_budget

    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    asked, charged = [], []
    monkeypatch.setattr(service, "run_public_chat", lambda *a, **k: asked.append(1) or "antwoord")
    monkeypatch.setattr(chat_char_budget, "charge", lambda request, n, **k: charged.append(n))

    too_long = "a" * (settings.chat_max_input_chars + 1)
    r = client.post("/raakje/vraag", data={"vraag": too_long})

    assert not asked, "the provider was asked"
    assert not charged, "the day's budget was charged for a refused question"
    assert r.status_code == 200
    assert f"max {settings.chat_max_input_chars} tekens" in r.text
    assert r.headers.get("X-Raakje-Failed") == "1", "the field does not keep the question"

    # A question of exactly the cap passes.
    r = client.post("/raakje/vraag", data={"vraag": "a" * settings.chat_max_input_chars})
    assert asked == [1] and charged == [settings.chat_max_input_chars]


def test_the_field_carries_the_cap_as_its_maxlength(client, monkeypatch):
    """The same number, from the setting: the browser stops the typing where the
    route would refuse. Proven red (8 October 2026): `max_chars` not passed by
    the widget → no `maxlength` on the field."""
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "chat_max_input_chars", 1234)
    home = client.get("/").text
    field = home[home.index('id="raakje-widget-vraag"') - 400 :][:900]
    assert 'maxlength="1234"' in field, field


# ── Provider-swap: Mock loopt de volledige tool-loop af ──────────────────────


def test_chat_disabled_returns_404(client, monkeypatch):
    """Hoofdschakelaar uit (default) → het endpoint bestaat 'niet'."""
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", False)
    r = client.post("/raakje/vraag", data={"vraag": "Hallo"})
    assert r.status_code == 404


def test_chat_endpoint_mock_simple_answer(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    r = client.post("/raakje/vraag", data={"vraag": "Wie zijn jullie?"})
    assert r.status_code == 200
    assert "Raakje" in r.text


def test_chat_endpoint_mock_runs_tool_loop(client, db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    # Een activiteit zodat de tool data heeft.
    _activity(db_session, "Quiz", date.today() + timedelta(days=5))

    r = client.post("/raakje/vraag", data={"vraag": "Welke activiteiten zijn er?"})
    assert r.status_code == 200
    # De data-bewuste mock toont de echte opgehaalde activiteit in het antwoord.
    assert "Quiz" in r.text
