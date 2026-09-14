"""Raakje in the back office: the guards around it (#917, CR-07).

Four mechanisms are new here, and each of them is the kind that fails silently:
the exposure fence in the assistant layer, the guard on the provider seam, the
outbound log, and the two separate tool allowlists. The masking itself — token
out, name back, question scrubbed — has its own file,
`test_assistant_masking.py`. A broken one of those does not
crash anything — it just sends a little more than it should, to a third party, and
nobody notices. So each is tested by breaking it on purpose and watching the test
go red, as the docstrings record.

What is deliberately NOT tested here is whether the model answers well. That is
the evaluation harness (`test_assistant_evaluation.py` and its by-hand run against
a real key); these tests are about what leaves the building, which has to hold
whichever model is on the other end.
"""
import json

import pytest
from sqlalchemy import text as sql_text

from app.domains.chatbot.providers.base import AssistantMessage, ToolCall
from app.domains.chatbot.seam import (
    GuardedProvider, SeamBlocked, admin_rules, findings, public_rules,
)
from app.domains.reporting.assistant import (
    CAPABILITY, TOOL_SPECS, build_system_prompt, dispatcher,
)

TENANT = 2


class Recorder:
    """A provider that records what it was handed and answers nothing useful.

    The payload as the provider received it is the only honest place to look: a
    test that inspects what the guard *thinks* it sent would pass a guard that
    sends something else.
    """

    name = "recorder"
    model = "recorder-1"

    def __init__(self, replies=None):
        self.calls: list[list[dict]] = []
        self._replies = list(replies or [])

    def complete(self, messages, tools=None, tool_choice=None):
        self.calls.append([dict(m) for m in messages])
        if self._replies:
            return self._replies.pop(0)
        return AssistantMessage(content="klaar", usage={"prompt": 11,
                                                        "completion": 7})

    @property
    def text(self) -> str:
        return json.dumps(self.calls, ensure_ascii=False, default=str)


def _assign_board_member(db, person):
    """Make this person the board member of a household, so `d_board_member`
    knows them — the view is built from the assignment, not from the person."""
    from app.domains.mdm.api import Member

    member = Member(tenant_id=TENANT, board_member_id=person.id)
    db.add(member)
    db.flush()
    return member


def _person(db, first: str, last: str):
    from app.domains.mdm.api import Member, MemberPerson, Person

    member = Member(tenant_id=TENANT)
    db.add(member)
    db.flush()
    person = Person(tenant_id=TENANT, first_name=first, last_name=last)
    db.add(person)
    db.flush()
    db.add(MemberPerson(tenant_id=TENANT, member_id=member.id,
                        person_id=person.id, relation_type="HOOFDLID"))
    db.flush()
    return person


# ── The exposure fence sits in the assistant, not in the engine ──────────────

def test_free_text_never_reaches_a_model(db_session):
    """The `none` objects, refused by name and with a usable reason.

    Free text cannot be classified field by field and there is no token to put on
    it — a treasurer's note carries whatever the treasurer wrote. So unlike the
    person-naming objects, there is no later phase in which this becomes allowed,
    and the refusal says exactly that rather than sounding temporary.

    Named and not merely blocked: the model reads the refusal and composes its
    next attempt from it (#680, applied to a reader that is a machine).

    Broken to see it red: `_REFUSED` emptied — the notes then come back as rows,
    and the test names the first object that got through.
    """
    from app.domains.reporting.universe import AiExposure, OBJECTS

    dispatch = dispatcher(tenant_id=TENANT)
    vrije_tekst = [o for o in OBJECTS if o.ai_exposure is AiExposure.NONE]
    assert len(vrije_tekst) >= 4, (
        "deze test draait over de objecten die nooit naar een model mogen; vindt "
        "ze er bijna geen, dan is de classificatie stuk en bewijst de test niets"
    )

    for obj in vrije_tekst:
        out = json.loads(dispatch("run_report", {"objects": [obj.key]}, db_session))
        assert "error" in out, f"{obj.key} werd niet geweigerd"
        assert obj.name in out["error"], (
            f"de weigering van {obj.key} noemt het object niet: {out['error']}"
        )
        assert "rows" not in out


def test_the_refusal_also_covers_a_filter_on_such_an_object(db_session):
    """Filtering on free text is asking for free text, one step later.

    A selection of `member_municipality` filtered on a treasurer's note carries no
    note in its columns — and would tell the model, row by row, which municipality
    the households with that note live in. The fence therefore reads the filters
    too.

    Broken to see it red: the `filter_keys` line dropped from `run_report`; the
    call then succeeds and this test fails on the missing refusal.
    """
    dispatch = dispatcher(tenant_id=TENANT)
    out = json.loads(dispatch("run_report", {
        "objects": ["payment_method", "payment_count"],
        "filters": [{"object": "payment_note", "operator": "contains",
                     "values": ["herinnering"]}],
    }, db_session))
    assert "error" in out and "Notitie" in out["error"]


def test_list_values_hands_back_tokens_and_never_names(db_session):
    """The values of a person-naming dimension ARE names (CR-07 §4.2).

    Worth its own test because it is the gap that would be easy to leave: the
    tokenisation was written for `run_report`, and `list_values` is a different
    function reaching the same data by another road. A tool result is a tool
    result, whichever tool produced it.

    Broken to see it red: the `_TOKENISED` branch removed from `list_values` —
    the seeded surname then comes back in the value list, which is the second
    assertion.
    """
    persoon = _person(db_session, "Mira", "Vandenbulcke")
    _assign_board_member(db_session, persoon)
    dispatch = dispatcher(tenant_id=TENANT)
    out = json.loads(dispatch("list_values", {"object": "board_member"},
                              db_session))
    assert "Vandenbulcke" not in json.dumps(out)
    assert any(v.startswith("persoon-") for v in out["values"]), out


def test_the_query_panel_still_shows_what_the_assistant_refuses(db_session):
    """The fence is the assistant's, not the engine's (CR-07 §9).

    If this ever goes red, someone moved the refusal down into `build_query` and
    took the household name out of the reports panel on the way — a screen that
    has every right to show it, behind the same admin door it always had.
    """
    from app.domains.reporting.api import build_query

    plan = build_query(_selection(["member_head_name", "member_total_count"]),
                       tenant_id=TENANT)
    assert plan.sql, "het paneel moet dit object gewoon kunnen tonen"


def _selection(keys):
    from app.domains.reporting.api import selection_from_dict

    return selection_from_dict({"objects": list(keys), "layout": "table"})


# ── Two allowlists, two dispatchers (CR-07 §6.2) ─────────────────────────────

def test_the_public_bot_cannot_run_a_report(db_session):
    """The surfaces share a loop and nothing else.

    Broken to see it red: `run_report` added to the public `TOOL_SPECS` — the
    public dispatcher then reaches a reporting tool from a page with no login.
    """
    from app.domains.chatbot.tools import ALLOWED_TOOLS, execute_tool

    assert "run_report" not in ALLOWED_TOOLS
    out = json.loads(execute_tool("run_report", {"objects": ["member"]}, db_session))
    assert "error" in out and "run_report" in out["error"]


def test_the_assistant_cannot_submit_an_idea(db_session):
    """And the other way round: the admin kit holds no write path at all."""
    out = json.loads(dispatcher(tenant_id=TENANT)(
        "submit_idea", {"name": "T", "content": "c", "email": "t@example.org"},
        db_session))
    assert "error" in out and "submit_idea" in out["error"]


# ── The guard on the seam (CR-07 §5.8) ───────────────────────────────────────

def test_a_name_from_the_administration_blocks_the_call(db_session):
    """The planted-name probe §5 asks for, end to end.

    The name is typed into the question — the channel phase 2 will scrub, and
    which is wide open until it does. The guard is what stands there in the
    meantime, and what will still stand there when the scrub has a hole in it.

    Broken to see it red: `match_names=False` in `admin_rules` — the surname then
    reaches the recorder, and the second assertion names it.
    """
    from app.domains.mdm.api import person_name_parts

    _person(db_session, "Mira", "Vandenbulcke")
    inner = Recorder()
    guarded = GuardedProvider(
        inner, admin_rules(lambda: person_name_parts(db_session),
                           capability=CAPABILITY))

    try:
        guarded.complete([{"role": "user",
                           "content": "Stopt het gezin Vandenbulcke dit jaar?"}])
        raise AssertionError("de wachter liet dit door")
    except SeamBlocked as geblokkeerd:
        assert "niet verstuurd" in str(geblokkeerd)
        assert "naam uit de ledenadministratie" in str(geblokkeerd)
    assert inner.calls == [], "de oproep is toch vertrokken"
    assert "Vandenbulcke" not in inner.text


def test_the_blocked_message_does_not_repeat_the_name(db_session):
    """A guard that quotes what it caught writes it into a log and onto a screen.

    The one thing this mechanism exists to prevent is a name ending up where it
    does not belong; a refusal reading "de naam 'Vandenbulcke' mag niet" would put
    it in two more places.
    """
    from app.domains.mdm.api import person_name_parts

    _person(db_session, "Mira", "Vandenbulcke")
    guarded = GuardedProvider(
        Recorder(), admin_rules(lambda: person_name_parts(db_session),
                                capability=CAPABILITY))
    try:
        guarded.complete([{"role": "user", "content": "Vandenbulcke?"}])
        raise AssertionError("niet geblokkeerd")
    except SeamBlocked as geblokkeerd:
        assert "Vandenbulcke" not in str(geblokkeerd)


def test_the_public_bot_may_receive_a_name_and_an_email(db_session):
    """The asymmetry is deliberate, and it is the only one (CR-07 §5.8).

    A visitor types their own name and e-mail into the contact path on purpose; a
    global guard would block `submit_idea` on the first message it was built for.
    Without this test that asymmetry survives exactly until someone tidies it up.
    """
    _person(db_session, "Mira", "Vandenbulcke")
    messages = [{"role": "user",
                 "content": "Ik ben Mira Vandenbulcke, mira@example.org"}]
    assert findings(messages, public_rules()) == []


def test_a_phone_number_or_an_account_number_stops_both_surfaces(db_session):
    """Patterns are not about whose data it is — that data has no business here.

    The account number is the IBAN from the IBAN documentation, and deliberately
    so: any valid number would do, and this is a public repository, so the one
    number that is nobody's account is the right one to write down.
    """
    for rules in (public_rules(),
                  admin_rules(lambda: set(), capability=CAPABILITY)):
        assert "een telefoonnummer" in findings(
            [{"role": "user", "content": "bel me op 0473 12 34 56"}], rules)
        assert "een rekeningnummer" in findings(
            [{"role": "user", "content": "stort op BE68 5390 0754 7034"}], rules)


def test_the_system_prompt_is_exempt_from_the_pattern_check(db_session):
    """Measured, not assumed — this is why the exemption exists.

    The first run of the guard blocked every public question, and the culprit was
    the privacy page in the system prompt: the association's own e-mail address and
    its own IBAN, published on purpose, because without a bank account the bot
    cannot say where the membership fee goes. A guard that blocks that protects
    nothing and breaks everything, and gets switched off within the week.

    The typed question and every tool result stay fully covered — those are the two
    channels along which administration data can actually leave.
    """
    prompt = [{"role": "system",
               "content": "IBAN: BE68 5390 0754 7034 · info@example.org"}]
    rules = admin_rules(lambda: set(), capability=CAPABILITY)
    assert findings(prompt, rules) == []
    assert findings(prompt + [{"role": "user", "content": "BE68 5390 0754 7034"}],
                    rules) != []


def test_the_name_check_covers_the_system_prompt_unless_a_pack_earns_otherwise(
        db_session):
    """The default is: scan everything. Deviating from it has to be argued.

    The system prompt is not always a fixed string. For the public bot it is built
    from tenant content — CMS pages, notes somebody typed into the AI context
    screen — and the day one of those carries a member's name, the name check is
    the only line standing there, because the pattern check has been told to look
    away. So `scan_prompt_names` defaults to True: a pack that says nothing about
    its prompt gets the full check.

    Turning it off is allowed for a prompt that is RENDERED rather than stored, and
    that claim is proven in `test_assistant_masking.py`, not asserted here.

    Raised by the brainstorm session on 13 September 2026; sharpened on 14
    September when the full scan turned out to block every question on HDEV.

    Broken to see it red: `scan_prompt_names: bool = False` as the dataclass
    default — a new pack would then silently ship without the check.
    """
    _person(db_session, "Mira", "Vandenbulcke")
    from app.domains.mdm.api import person_name_parts

    prompt = [{"role": "system",
               "content": "Nota van het bestuur: Vandenbulcke belt nog terug."}]
    namen = lambda: person_name_parts(db_session)  # noqa: E731

    standaard = admin_rules(namen, capability=CAPABILITY)
    assert standaard.scan_prompt_names is True
    assert findings(prompt, standaard) != []

    verdiend = admin_rules(namen, capability=CAPABILITY, scan_prompt_names=False)
    assert findings(prompt, verdiend) == []
    # En wat de gebruiker typt blijft onverkort gescand, ook dan.
    assert findings(prompt + [{"role": "user", "content": "Vandenbulcke?"}],
                    verdiend) != []


def test_a_name_particle_does_not_make_every_sentence_suspect(db_session):
    """Measured on HDEV, and it stopped the assistant answering anything.

    One household called "Van den Broeck" puts `van` and `den` into the name list.
    The catalogue that travels with every question is twenty thousand characters of
    Dutch, so every single question collided — three hits, always the same three,
    whatever the admin typed. To the person using it that is not protection, it is
    a broken assistant, and a check like that gets switched off.

    A particle points at nobody, so it is not a name in the sense this list means.
    A surname that happens to be an ordinary word — Bos, Mol — stays in: that is
    the known false block of CR-07 §5.8, and that side is the safe one.

    Broken to see it red: `NAME_PARTICLES` emptied — `van` is then back in the
    list and the first assertion fails.
    """
    from app.domains.mdm.api import person_name_parts

    _person(db_session, "Jan", "Van den Broeck")
    delen = person_name_parts(db_session)

    assert "van" not in delen and "den" not in delen
    assert "broeck" in delen, "de naam zelf moet wél herkend blijven"
    assert "jan" in delen

    rules = admin_rules(lambda: delen, capability=CAPABILITY)
    gewoon = [{"role": "user", "content": "Wat is de omzet van de activiteiten?"}]
    assert findings(gewoon, rules) == []
    echt = [{"role": "user", "content": "Stopt het gezin Broeck?"}]
    assert findings(echt, rules) != []


# ── The outbound log (CR-07 §6.4) ────────────────────────────────────────────
#
# The log sink commits in its OWN session, so its rows survive the SAVEPOINT the
# test fixture rolls back — which is exactly the behaviour these tests are here to
# prove. The price is that the table has to be emptied by hand between them, or the
# second test counts the first one's row and the failure reads as a bug in the code
# instead of in the test.


@pytest.fixture
def leeg_logboek():
    from app.database import SessionLocal

    def wis():
        eigen = SessionLocal()
        try:
            eigen.execute(sql_text("DELETE FROM ai.ai_call_log"))
            eigen.commit()
        finally:
            eigen.close()

    wis()
    yield
    wis()


def _log_rows(db):
    return db.execute(sql_text(
        "SELECT surface, capability, actor, model, payload, tokens_prompt, "
        "tokens_completion, blocked_reason FROM ai.ai_call_log ORDER BY id"
    )).mappings().all()


def test_every_outbound_call_lands_in_the_log_with_its_token_usage(db_session, leeg_logboek):
    """One row per call, and the cost question answered for both surfaces at once.

    Token usage was returned by Mistral on every response and thrown away; logging
    at the seam is what makes "wat kost de AI deze maand?" one query instead of an
    estimate.

    The sink writes in its own session on purpose, so this test reads the row back
    over a raw connection rather than through the test session.
    """
    from app.domains.chatbot.logbook import sink_for

    guarded = GuardedProvider(Recorder(), public_rules(), sink_for())
    guarded.complete([{"role": "user", "content": "hallo"}])

    rows = _log_rows(db_session)
    assert len(rows) == 1
    rij = rows[0]
    assert rij["surface"] == "public"
    assert rij["tokens_prompt"] == 11 and rij["tokens_completion"] == 7
    assert rij["blocked_reason"] == ""
    assert "hallo" in rij["payload"]


def test_a_blocked_call_is_logged_as_blocked(db_session, leeg_logboek):
    """The call that never happened is the row you most want afterwards.

    Broken to see it red: the `self._log(...)` line in the blocking branch removed
    — the table then stays empty and nothing anywhere records that somebody asked
    for a name.
    """
    from app.domains.chatbot.logbook import sink_for
    from app.domains.mdm.api import person_name_parts

    _person(db_session, "Mira", "Vandenbulcke")
    guarded = GuardedProvider(
        Recorder(),
        admin_rules(lambda: person_name_parts(db_session), capability=CAPABILITY),
        sink_for("bestuur@example.org"))
    try:
        guarded.complete([{"role": "user", "content": "gezin Vandenbulcke?"}])
    except SeamBlocked:
        pass

    rows = _log_rows(db_session)
    assert len(rows) == 1
    assert rows[0]["surface"] == "admin"
    assert rows[0]["capability"] == "reporting"
    assert rows[0]["actor"] == "bestuur@example.org"
    assert "naam uit de ledenadministratie" in rows[0]["blocked_reason"]


# ── Caps (CR-07 §4.2) ────────────────────────────────────────────────────────

def test_a_long_result_is_cut_and_says_so(db_session):
    """Cut with a marker, never silently.

    A model handed fifty rows of two hundred has no way to know, and will answer
    "in totaal" over a page. The marker is the difference between a capped answer
    and a wrong one.
    """
    from tests._reporting_seed import seed

    seed(db_session)
    out = json.loads(dispatcher(tenant_id=TENANT, max_rows=1)(
        "run_report", {"objects": ["payment_method", "payment_count"]}, db_session))
    assert out["row_count"] == 1
    assert "truncated" in out and "Verfijn" in out["truncated"]


def test_the_wall_clock_ends_a_stuck_conversation(db_session):
    """A spinner that never stops is the worst of both worlds (CR-07 §4.3)."""
    import time

    from app.domains.chatbot.service import ChatTimeout, run_chat

    slow = Recorder(replies=[AssistantMessage(
        tool_calls=[ToolCall(id="1", name="list_values",
                             arguments={"object": "payment_status"})])])
    try:
        run_chat(db_session, [{"role": "user", "content": "?"}], slow,
                 max_rounds=3, tools=TOOL_SPECS,
                 dispatch=dispatcher(tenant_id=TENANT),
                 deadline=time.monotonic() - 1)
        raise AssertionError("de wandklok deed niets")
    except ChatTimeout as op:
        assert "te lang" in str(op)
    assert slow.calls == []


# ── The catalogue (CR-07 §5.1) ───────────────────────────────────────────────

def test_the_catalogue_is_rendered_from_the_declaration(db_session):
    """One source for the human document and the machine catalogue.

    Not a copy of `docs.py` and not a copy of the panel: both read the same
    tuples. So the check that matters is that every object the universe has is
    reachable from the catalogue text, refused ones included — a model that cannot
    see an object guesses at a key, and a guess costs a round.

    Broken to see it red: one object's line dropped from the renderer.
    """
    from app.domains.reporting.universe import OBJECTS

    catalogue = build_system_prompt()
    ontbreekt = [o.key for o in OBJECTS if f"`{o.key}`" not in catalogue]
    assert not ontbreekt, f"niet in de catalogus: {ontbreekt[:5]}"
    assert "GEWEIGERD" in catalogue
    # The money default is declared rather than assumed (CR-07 §7).
    assert "GEFACTUREERDE" in catalogue
    # En de verwijderde drempel spookt er niet meer in rond (14 september 2026):
    # een instructie over samenvoegen zou het model laten schrijven dat er
    # samengevoegd is terwijl dat niet gebeurt.
    assert "privacydrempel" not in catalogue
    assert "Samengevoegd" not in catalogue
