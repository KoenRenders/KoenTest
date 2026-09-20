"""Raakje bound to one activity (#975) — the boundary lives on the server.

A filter that only exists in the question or the system prompt is not a boundary:
the model can forget it, ignore it, or talk around it. So the activity mode binds
every tool call in the dispatcher, and these tests drive the dispatcher the way a
model would — including the ways a model gets it wrong.

Three paths can reach an activity: `run_report`, `get_activities` and
`get_activity_detail`. Each has its own test here, because a boundary that holds
on two of three roads is not a boundary. `get_activities` is the treacherous one:
it returns a list by nature.

The data is the evaluation seed: a Quiz (6 places, €30, paid) and a Wandeling
(5 places, €20, not paid), both at the same tenant.
"""
import json

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.reporting.assistant import (ACTIVITY_FACTS, SCOPE_COUNT_MEASURE,
                                             build_system_prompt, dispatcher,
                                             scope_for_activity)
from tests._assistant_seed import TENANT, seed
from tests.conftest import SEEDED_ADMIN_EMAIL


@pytest.fixture
def situatie(db_session):
    return seed(db_session)


def _scoped(situatie, naam="quiz"):
    return dispatcher(tenant_id=TENANT,
                      scope=scope_for_activity(situatie["activities"][naam]))


def _call(dispatch, db, name, args):
    return json.loads(dispatch(name, args, db))


# ── run_report ───────────────────────────────────────────────────────────────

def test_a_report_without_a_filter_still_covers_only_this_activity(db_session,
                                                                   situatie):
    """The test that matters (#975): the model leaves the filter out.

    Broken to see it red: the line that appends the `activity_id` filter in
    `_scope_report` removed — both activities come back, and the Wandeling row
    is what the second assertion names. Measured: this test and three others
    (filter-on-this-activity, values, the route) turn red.
    """
    out = _call(_scoped(situatie), db_session, "run_report",
                {"objects": ["activity", "registration_quantity"]})

    namen = [r["activity"] for r in out["rows"]]
    assert namen == ["Quiz"], out
    assert "Wandeling" not in json.dumps(out)
    assert out["totals"]["registration_quantity"] == 6


def test_a_filter_on_another_activity_is_refused_with_the_reason(db_session,
                                                                 situatie):
    for filt in ({"object": "activity", "operator": "eq", "values": ["Wandeling"]},
                 {"object": "activity_id", "operator": "eq",
                  "values": [str(situatie["activities"]["wandeling"])]}):
        out = _call(_scoped(situatie), db_session, "run_report",
                    {"objects": ["registration_quantity"], "filters": [filt]})
        assert "error" in out, filt
        assert "één activiteit" in out["error"]


def test_a_filter_on_this_activity_costs_no_round(db_session, situatie):
    """Refusing the model for being explicit about the right activity would cost a
    round for nothing.

    And it is dropped rather than kept: a name filter compares text, so "quiz"
    would find nothing where the activity is called "Quiz". Measured — the first
    version kept it and returned no rows.
    """
    out = _call(_scoped(situatie), db_session, "run_report",
                {"objects": ["activity", "registration_quantity"],
                 "filters": [{"object": "activity", "operator": "eq",
                              "values": ["quiz"]}]})
    assert "error" not in out, out
    assert [r["activity"] for r in out["rows"]] == ["Quiz"]


def test_a_fact_that_does_not_hang_on_an_activity_is_refused_by_name(db_session,
                                                                     situatie):
    """Memberships have no activity. The engine would refuse too, but with a
    message about a dimension the model cannot act on."""
    out = _call(_scoped(situatie), db_session, "run_report",
                {"objects": ["membership_households"]})
    assert "error" in out
    assert "één activiteit" in out["error"]
    assert "Lidmaatschappen" in out["error"]


def test_values_come_from_this_activity_only(db_session, situatie):
    """`list_values` reads a whole dimension; in this mode it reads the scope.

    The Quiz is paid and the Wandeling is not, so the payment status of the Quiz
    has one value — and the unscoped list would have two.
    """
    scoped = _call(_scoped(situatie), db_session, "list_values",
                   {"object": "payment_status"})
    alles = _call(dispatcher(tenant_id=TENANT), db_session, "list_values",
                  {"object": "payment_status"})

    assert scoped["values"] == ["Betaald"], scoped
    assert set(alles["values"]) >= {"Betaald", "In afwachting"}


def test_a_list_of_activities_is_not_offered_in_scope(db_session, situatie):
    out = _call(_scoped(situatie), db_session, "list_values", {"object": "activity"})
    assert "error" in out and "één activiteit" in out["error"]


# ── de publieke leestools ────────────────────────────────────────────────────

def test_get_activities_shows_only_this_activity(db_session, situatie):
    """The side door (#975): a tool that returns a list by nature.

    Broken to see it red: the `activities` filter in `_scoped_read_tool` removed —
    the Wandeling is then in the list.
    """
    dispatch = _scoped(situatie)
    gezien = []
    for when in ("upcoming", "past"):
        out = _call(dispatch, db_session, "get_activities", {"when": when})
        gezien += [a["name"] for a in out["activities"]]

    assert gezien == ["Quiz"], gezien


def test_get_activity_detail_is_bound_to_this_activity(db_session, situatie):
    dispatch = _scoped(situatie)

    eigen = _call(dispatch, db_session, "get_activity_detail", {})
    assert eigen["name"] == "Quiz", "zonder id valt de tool terug op de scope"

    ander = _call(dispatch, db_session, "get_activity_detail",
                  {"activity_id": situatie["activities"]["wandeling"]})
    assert "error" in ander and "één activiteit" in ander["error"]


def test_the_admin_can_read_what_the_public_bot_reads(db_session, situatie):
    """Koen, 16 September 2026: *"Die mag alles van de publieke + reporting."*

    Unscoped here — the general admin assistant gains the read tools too.
    """
    out = _call(dispatcher(tenant_id=TENANT), db_session, "get_activity_detail",
                {"activity_id": situatie["activities"]["wandeling"]})
    assert out["name"] == "Wandeling"


def test_the_admin_kit_holds_no_write_tool(db_session, situatie):
    """Read only (#975). `submit_idea` creates a message and a task — not lent."""
    from app.domains.chatbot.tools import ALLOWED_TOOLS, execute_tool
    from app.domains.reporting.assistant import tool_specs

    namen = {s["function"]["name"] for s in tool_specs()}
    assert "submit_idea" not in namen
    out = _call(dispatcher(tenant_id=TENANT), db_session, "submit_idea",
                {"name": "T", "content": "c", "email": "t@example.org"})
    assert "error" in out and "submit_idea" in out["error"]
    # En de publieke kant kent nog altijd geen rapport (CR-07 §6.2).
    assert "run_report" not in ALLOWED_TOOLS
    assert "run_report" in json.loads(
        execute_tool("run_report", {}, db_session))["error"]


# ── wat er naar het model gaat ───────────────────────────────────────────────

def test_the_scoped_prompt_names_the_number_and_not_the_name(db_session, situatie):
    """The prompt of this pack is exempt from the name check because it carries no
    stored value. An activity name is stored content — so only the number goes in,
    and the name reaches the model through a tool, whose result IS scanned."""
    prompt = build_system_prompt(
        scope_for_activity(situatie["activities"]["quiz"]))
    assert f"nummer {situatie['activities']['quiz']}" in prompt
    assert "Quiz" not in prompt


def test_person_values_are_still_tokens_in_scope(db_session, situatie):
    """Scope does not weaken the masking (#975). With the small-cell threshold gone,
    the token is the only line on a row about one household."""
    # Payments hang on a household; registrations hang on a person.
    out = _call(_scoped(situatie), db_session, "run_report",
                {"objects": ["member", "payment_count"]})
    assert out.get("rows"), out
    assert all(str(r["member"]).startswith("gezin-") for r in out["rows"])


def test_every_activity_fact_has_a_count_for_scoped_values():
    """A fact that gains an activity link must also get a count here, or
    `list_values` in scope silently skips it."""
    assert set(SCOPE_COUNT_MEASURE) == set(ACTIVITY_FACTS)


# ── de route ─────────────────────────────────────────────────────────────────

def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


@pytest.fixture
def aan(db_session, monkeypatch):
    from app.config import settings
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    set_setting(db_session, "admin_chat_enabled", "1", tenant_id=TENANT)
    db_session.flush()


def _pad(activity_id):
    return f"/admin/rapporten/raakje/activiteit/{activity_id}"


def test_the_route_answers_about_this_activity_only(client, db_session, situatie, aan):
    kop = _login(client)
    resp = client.post(_pad(situatie["activities"]["quiz"]),
                       data={"vraag": "hoeveel inschrijvingen per activiteit?",
                             "historie": "[]"}, headers=kop)

    assert resp.status_code == 200
    assert "Quiz" in resp.text
    assert "Wandeling" not in resp.text.split("Wat zag Mistral?")[0]


def test_an_activity_of_another_tenant_is_not_found(client, db_session, situatie, aan):
    from datetime import date

    from app.domains.activities.api import Activity, ActivityDate

    vreemd = Activity(tenant_id=3, name="Elders")
    db_session.add(vreemd)
    db_session.flush()
    db_session.add(ActivityDate(tenant_id=3, activity_id=vreemd.id,
                                start_date=date.today()))
    db_session.flush()

    kop = _login(client)
    resp = client.post(_pad(vreemd.id), data={"vraag": "?", "historie": "[]"},
                       headers=kop)
    assert resp.status_code == 404
    assert "Activiteit niet gevonden" in resp.text


def test_an_activity_that_does_not_exist_is_not_found(client, db_session, situatie,
                                                      aan):
    kop = _login(client)
    resp = client.post(_pad(999_999), data={"vraag": "?", "historie": "[]"},
                       headers=kop)
    assert resp.status_code == 404


def test_off_is_off_in_the_activity_mode_too(client, db_session, situatie,
                                            monkeypatch):
    """Both switches, one route: the environment switch off → no answer."""
    from app.config import settings

    monkeypatch.setattr(settings, "admin_chat_enabled", False)
    kop = _login(client)
    resp = client.post(_pad(situatie["activities"]["quiz"]),
                       data={"vraag": "?", "historie": "[]"}, headers=kop)
    assert resp.status_code == 404
    assert "Niet gevonden" in resp.text


def test_the_tenant_switch_off_is_off_too(client, db_session, situatie, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    kop = _login(client)
    resp = client.post(_pad(situatie["activities"]["quiz"]),
                       data={"vraag": "?", "historie": "[]"}, headers=kop)
    assert resp.status_code == 404


def test_the_route_needs_csrf(client, db_session, situatie, aan):
    _login(client)
    resp = client.post(_pad(situatie["activities"]["quiz"]),
                       data={"vraag": "?", "historie": "[]"})
    assert resp.status_code == 403
    assert "CSRF" in resp.text
