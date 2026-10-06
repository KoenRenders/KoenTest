"""Raakje proposes name, location, description and date for an activity (#1604).

No model: every answer is scripted, and the real `GuardedProvider` still wraps
the stand-in, so the guard and the cost registration run as they do live.

What these prove, each red when its rule is taken out (5 October 2026):

- a request naming a place and a day yields a proposal for name, location,
  description and one date row — red on master (no route, no proposer);
- a location and a date that stand in neither the request nor the record are
  not proposed and are named — broken by accepting every location / by
  skipping the `date_source` check;
- the date fields name the GROUP and never a row: the second date of the
  record appears nowhere in the proposal — broken by naming the row's key;
- a sentence the verification names, and a number no source holds, is left out
  of the value and offered with an unticked "klopt, behouden";
- a name from the member administration never reaches the model;
- the route writes nothing, answers 404 with Raakje switched off, and the call
  is registered under a capability of its own.
"""

from __future__ import annotations

import json
import re
from datetime import date, time

import pytest

from app.domains.activities import proposer
from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.chatbot.providers.base import AssistantMessage
from app.domains.reporting.assistant_context import context_for
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

TODAY = date(2026, 10, 5)
REQUEST = "Een herfstwandeling met soep op zaterdag 14 november om 14 uur in de parochiezaal."


class ScriptedProvider:
    """Answers in order; keeps every message list it was asked."""

    # A stand-in logs as the `mock` provider: the AI log only takes known codes.
    name = "mock"
    model = "scripted"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked: list[list[dict]] = []

    def complete(self, messages, tools=None, tool_choice=None):
        self.asked.append([dict(m) for m in messages])
        answer = self.answers.pop(0) if self.answers else json.dumps({"unsupported": []})
        if isinstance(answer, Exception):
            raise answer
        return AssistantMessage(content=answer)

    def payloads(self) -> str:
        return json.dumps(self.asked, ensure_ascii=False).lower()


@pytest.fixture
def raakje(monkeypatch):
    def install(*answers):
        provider = ScriptedProvider(*answers)
        monkeypatch.setattr("app.domains.chatbot.api.get_provider", lambda model="": provider)
        return provider

    return install


def _answer(**fields) -> str:
    return json.dumps({"reply": "Voorstel klaar.", **fields}, ensure_ascii=False)


def _verdict(*items) -> str:
    return json.dumps({"unsupported": [{"sentence": n, "reason": why} for n, why in items]})


FULL = dict(
    name="Herfstwandeling met soep",
    location="Parochiezaal",
    description="Kom mee wandelen door de herfst. Achteraf is er soep in de parochiezaal.",
    date={"start_date": "2026-11-14", "start_time": "14:00"},
    date_source="zaterdag 14 november om 14 uur",
)


def _activity(db, *, dates=(), name="Wandeling", location=None, description=None) -> Activity:
    activity = Activity(name=name, location=location, description=description)
    db.add(activity)
    db.flush()
    for day, begins in dates:
        db.add(ActivityDate(activity_id=activity.id, start_date=day, start_time=begins))
    db.flush()
    db.refresh(activity)
    return activity


def _propose(db, activity, request=REQUEST):
    return proposer.propose(db, activity, request=request, actor="s@example.org", today=TODAY)


def _by_name(proposal) -> dict:
    return {f["name"]: f for f in proposal.fields}


# ── The proposal ─────────────────────────────────────────────────────────────


def test_a_request_with_a_place_and_a_day_proposes_four_fields_and_one_date_row(db_session, raakje):
    raakje(_answer(**FULL), _verdict())
    activity = _activity(db_session)

    proposal = _propose(db_session, activity)

    fields = _by_name(proposal)
    assert list(fields) == ["name", "location", "description", "start_date", "start_time"]
    assert fields["name"]["value"] == "Herfstwandeling met soep"
    assert fields["name"]["base"] == "Wandeling", "the base is what the record holds"
    assert fields["location"]["value"] == "Parochiezaal" and fields["location"]["base"] == ""
    assert fields["description"]["value"] == FULL["description"]
    assert "parts" not in fields["description"], "nothing marked, so nothing to tick"
    # the date: the first row of the group, empty bases — there is no row yet
    for name, value in (("start_date", "2026-11-14"), ("start_time", "14:00")):
        assert fields[name]["group"] == "d_order" and fields[name]["value"] == value
        assert fields[name]["base"] == ""
    assert fields["start_date"]["shown"] == "zaterdag 14 november 2026"
    assert proposal.left_out == [] and proposal.marks == [] and not proposal.unverified


def test_a_location_and_a_date_nobody_gave_are_not_proposed_and_are_named(db_session, raakje):
    """The stubbed model invents both. Neither stands in the request or in the
    record, so neither becomes a field, and the panel says so."""
    raakje(
        _answer(
            name="Herfstwandeling",
            location="Gemeentehuis Wommelgem",
            date={"start_date": "2026-12-01", "start_time": "19:30"},
            date_source="dinsdag 1 december",
        )
    )
    activity = _activity(db_session)

    proposal = _propose(db_session, activity, request="Stel een betere naam voor.")

    assert list(_by_name(proposal)) == ["name"]
    assert len(proposal.left_out) == 3, "the place, the day and the hour, each on its own"
    assert proposal.left_out[0].startswith("Locatie: niet voorgesteld")
    assert proposal.left_out[1].startswith("Datum (dinsdag 1 december 2026): niet voorgesteld")
    assert proposal.left_out[2].startswith("Van (19:30): niet voorgesteld")


def test_a_date_without_the_passage_it_was_read_from_is_not_proposed(db_session, raakje):
    """Even a date that happens to match the request needs its passage: the
    passage is what ties it to a source."""
    raakje(_answer(date={"start_date": "2026-11-14"}))
    proposal = _propose(db_session, _activity(db_session))
    assert proposal.fields == []
    assert proposal.left_out and proposal.left_out[0].startswith("Datum (zaterdag 14 november")


def test_a_relative_day_is_a_source_and_what_the_record_holds_is_one_too(db_session, raakje):
    raakje(
        _answer(
            location="Dorpsplein 3",
            date={"start_date": "2026-10-10"},
            date_source="Volgende  zaterdag",
        )
    )
    activity = _activity(db_session, description="We vertrekken op Dorpsplein 3.")

    proposal = _propose(db_session, activity, request="Het is volgende zaterdag.")

    fields = _by_name(proposal)
    assert fields["start_date"]["value"] == "2026-10-10", "case and spacing aside, it stands there"
    assert fields["location"]["value"] == "Dorpsplein 3", "every word stands in the record"
    assert proposal.left_out == []


def test_the_date_names_the_group_and_no_other_row(db_session, raakje):
    """Two dates in the record. The proposal moves the first: its fields carry
    the first row's values as their base and name the group — the second date
    stands nowhere in what the page gets, so it cannot be touched."""
    raakje(
        _answer(
            date={"start_date": "2026-11-21", "start_time": "10:00", "end_time": "12:00"},
            date_source="zaterdag 21 november van 10 tot 12 uur",
        )
    )
    activity = _activity(
        db_session,
        dates=((date(2026, 11, 28), time(20, 0)), (date(2026, 11, 14), time(14, 0))),
    )

    proposal = _propose(
        db_session, activity, request="Verplaats naar zaterdag 21 november van 10 tot 12 uur."
    )

    fields = _by_name(proposal)
    assert list(fields) == ["start_date", "start_time", "end_time"]
    assert (fields["start_date"]["base"], fields["start_time"]["base"]) == ("2026-11-14", "14:00")
    assert fields["end_time"]["base"] == ""
    sent = json.dumps(proposal.fields)
    assert "2026-11-28" not in sent and "20:00" not in sent
    assert all(f["group"] == "d_order" for f in proposal.fields)
    assert not re.search(r"d\.\d+\.", sent), "a row key in a field name"


def test_what_the_record_holds_already_is_not_proposed_again(db_session, raakje):
    raakje(
        _answer(
            name="Wandeling",
            location="Parochiezaal",
            date={"start_date": "2026-11-14", "start_time": "15:00"},
            date_source="om 15 uur",
        )
    )
    activity = _activity(
        db_session, location="Parochiezaal", dates=((date(2026, 11, 14), time(14, 0)),)
    )
    proposal = _propose(db_session, activity, request="Het begint om 15 uur.")
    assert list(_by_name(proposal)) == ["start_time"]
    assert proposal.left_out == []


# ── A day and an hour are two facts (#1650) ──────────────────────────────────

#: What Koen asked on HDEV on 6 October 2026, and was told that "date and time"
#: stood nowhere.
KOEN = (
    "Vul je een andere datum in? Ik bedoel uur. We zouden willen gaan schaatsen "
    "van 10 uur in de voormiddag tot 12 uur smiddags."
)


def test_hours_without_a_day_go_on_the_date_row_that_is_there(db_session, raakje):
    """Red on master: the answer carried no passage for a DATE, so the hours
    went with it — "Datum en uur: niet voorgesteld"."""
    raakje(_answer(date={"start_time": "10:00", "end_time": "12:00"}))
    activity = _activity(db_session, dates=((date(2026, 11, 8), time(14, 0)),))

    proposal = _propose(db_session, activity, request=KOEN)

    fields = _by_name(proposal)
    assert list(fields) == ["start_time", "end_time"], "the day is left alone"
    assert (fields["start_time"]["value"], fields["start_time"]["base"]) == ("10:00", "14:00")
    assert (fields["end_time"]["value"], fields["end_time"]["base"]) == ("12:00", "")
    assert all(f["group"] == "d_order" for f in proposal.fields)
    assert proposal.left_out == []


def test_hours_on_a_record_without_a_date_come_on_a_new_row_and_the_day_is_named(
    db_session, raakje
):
    raakje(_answer(date={"start_time": "10:00", "end_time": "12:00"}))
    proposal = _propose(db_session, _activity(db_session), request=KOEN)

    fields = _by_name(proposal)
    assert list(fields) == ["start_time", "end_time"]
    assert all(f["base"] == "" for f in proposal.fields), "an empty base: the page adds the row"
    assert proposal.left_out == [
        "De dag ontbreekt nog: het uur komt op een nieuwe datumrij, vul de datum zelf in."
    ]


def test_an_hour_nobody_gave_is_refused_alone_and_the_given_one_stays(db_session, raakje):
    """Each part on its own: the invented end takes nothing with it, and the
    line names it by its clock time."""
    raakje(_answer(date={"start_time": "10:00", "end_time": "17:30"}))
    activity = _activity(db_session, dates=((date(2026, 11, 8), None),))

    proposal = _propose(db_session, activity, request="We beginnen om 10 uur.")

    assert list(_by_name(proposal)) == ["start_time"]
    assert proposal.left_out == [
        "Tot (17:30): niet voorgesteld — staat niet in je vraag en niet in de fiche."
    ]


def test_an_invented_day_does_not_take_the_given_hours_with_it(db_session, raakje):
    raakje(
        _answer(
            date={"start_date": "2026-12-01", "start_time": "10:00", "end_time": "12:00"},
            date_source="van 10 tot 12",
        )
    )
    activity = _activity(db_session, dates=((date(2026, 11, 8), None),))

    proposal = _propose(db_session, activity, request="Van 10 tot 12, graag.")

    assert list(_by_name(proposal)) == ["start_time", "end_time"]
    assert len(proposal.left_out) == 1
    assert proposal.left_out[0].startswith("Datum (dinsdag 1 december 2026): niet voorgesteld")


def test_a_day_without_an_hour_is_the_mirror(db_session, raakje):
    """And the passage need not be one literal stretch: its words stand in the
    request, with others between them."""
    raakje(_answer(date={"start_date": "2026-11-21"}, date_source="zaterdag 21 november"))
    activity = _activity(db_session, dates=((date(2026, 11, 14), time(14, 0)),))

    proposal = _propose(db_session, activity, request="Verplaats het naar zaterdag, 21 november.")

    fields = _by_name(proposal)
    assert list(fields) == ["start_date"]
    assert (fields["start_date"]["value"], fields["start_date"]["base"]) == (
        "2026-11-21",
        "2026-11-14",
    )
    assert proposal.left_out == []


def test_when_the_model_reads_no_hour_the_panel_says_which_words_it_missed(db_session, raakje):
    """The second way Koen's request could fail: the model answers about the
    name. The panel then names the hours it was given, not "niet in je vraag"."""
    raakje(_answer(reply="Geef eventueel een nieuwe naam of omschrijving."))
    activity = _activity(db_session, dates=((date(2026, 11, 8), None),))

    proposal = _propose(db_session, activity, request=KOEN)

    assert proposal.fields == []
    assert len(proposal.left_out) == 1
    line = proposal.left_out[0]
    assert line.startswith("Uur: niet voorgesteld — Raakje las “10 uur, 12 uur” in je vraag niet")
    assert "van 10 tot 12 uur" in line


def test_a_request_without_an_hour_gets_no_remark_about_hours(db_session, raakje):
    raakje(_answer(name="Schaatsen"))
    proposal = _propose(db_session, _activity(db_session), request="Stel een betere naam voor.")
    assert proposal.left_out == []


@pytest.mark.parametrize(
    ("said", "clock"),
    [
        ("10 uur in de voormiddag", time(10, 0)),
        ("12 uur 's middags", time(12, 0)),
        ("12 uur smiddags", time(12, 0)),
        ("half drie", time(14, 30)),
        ("half 3", time(2, 30)),
        ("14u", time(14, 0)),
        ("14u30", time(14, 30)),
        ("14 u 30", time(14, 30)),
        ("om 20.15", time(20, 15)),
        ("19:45", time(19, 45)),
        ("kwart voor acht", time(19, 45)),
        ("kwart over 9", time(9, 15)),
        ("tien uur", time(10, 0)),
        ("van 10 tot 12", time(12, 0)),
        ("om 9", time(21, 0)),
        ("3 uur in de namiddag", time(15, 0)),
    ],
)
def test_a_spoken_hour_is_a_source_for_its_clock_time(said, clock):
    given, words = proposer.hours_in(f"We komen samen, {said}, aan de ingang.")
    assert clock in given, (said, sorted(given))
    assert words, "the words it was said in are kept for the panel"


@pytest.mark.parametrize(
    "text",
    [
        "We wandelen 8 kilometer.",
        "Tot 12 november kan je inschrijven.",
        "Op zaterdag 14 november in zaal 3.",
        "Het kost 5 euro, voor 20 deelnemers.",
        "Vul je een andere datum in?",
    ],
)
def test_a_number_that_is_no_hour_grounds_no_hour(text):
    assert proposer.hours_in(text) == (set(), [])


def test_the_hours_of_the_record_are_a_source_too(db_session, raakje):
    """ "Een uur later": no number in the request, but the record holds 14:00–16:00
    and the model moves the end to the hour the start had... which the record gives."""
    raakje(_answer(date={"end_time": "14:00"}))
    activity = _activity(db_session, dates=((date(2026, 11, 8), time(14, 0)),))
    proposal = _propose(db_session, activity, request="Zet het einduur gelijk aan het beginuur.")
    assert list(_by_name(proposal)) == ["end_time"] and proposal.left_out == []


# ── The description: marked and left out by default ──────────────────────────


def test_a_sentence_without_a_source_is_left_out_and_offered_with_a_tick(db_session, raakje):
    text = "Kom mee wandelen door de herfst. Er is een tombola. De eerste 20 deelnemers krijgen een cadeau."
    provider = raakje(_answer(description=text), _verdict((2, "staat niet in de vraag")))
    activity = _activity(db_session)

    proposal = _propose(db_session, activity)

    field = _by_name(proposal)["description"]
    assert field["value"] == "Kom mee wandelen door de herfst."
    assert [(p["text"], p["mark"]) for p in field["parts"]] == [
        ("Kom mee wandelen door de herfst.", None),
        ("Er is een tombola.", 2),
        ("De eerste 20 deelnemers krijgen een cadeau.", 3),
    ]
    assert [(m["id"], m["reason"]) for m in proposal.marks] == [
        (2, "staat niet in de vraag"),
        (3, "dit getal staat in geen enkele bron"),
    ]
    assert len(provider.asked) == 2, "the proposal and its verification"
    assert "1. kom mee wandelen" in provider.payloads()


def test_a_number_the_request_gave_is_not_marked(db_session, raakje):
    raakje(
        _answer(
            description="We wandelen 8 kilometer en starten om 14 uur.",
            date={"start_date": "2026-11-14", "start_time": "14:00"},
            date_source="zaterdag 14 november om 14 uur",
        )
    )
    proposal = _propose(
        db_session,
        _activity(db_session),
        request="8 kilometer wandelen op zaterdag 14 november om 14 uur.",
    )
    assert proposal.marks == []


def test_a_description_with_no_sourced_sentence_is_not_a_field(db_session, raakje):
    """A proposal must not empty a description that is there."""
    raakje(_answer(description="Er is een tombola."), _verdict((1, "staat nergens")))
    activity = _activity(db_session, description="Samen op pad.")
    proposal = _propose(db_session, activity)
    assert proposal.fields == [] and proposal.marks == []
    assert "Omschrijving: niet voorgesteld — geen enkele zin heeft een bron." in proposal.left_out


def test_a_failed_verification_says_the_proposal_was_not_checked(db_session, raakje):
    raakje(_answer(description="Kom mee wandelen."), RuntimeError("geen verbinding"))
    proposal = _propose(db_session, _activity(db_session))
    assert proposal.unverified
    assert _by_name(proposal)["description"]["value"] == "Kom mee wandelen."


def test_an_answer_that_is_no_json_is_an_error_for_the_screen(db_session, raakje):
    raakje("Dat weet ik niet.")
    with pytest.raises(proposer.ProposerError, match="geen bruikbaar voorstel"):
        _propose(db_session, _activity(db_session))


# ── Names and the prompt ─────────────────────────────────────────────────────


def test_a_known_name_never_leaves_and_never_comes_back(db_session, raakje):
    from app.domains.mdm.api import Person

    db_session.add(Person(first_name="Zebedeus", last_name="Quackenbosch"))
    db_session.flush()
    provider = raakje(_answer(name="Wandeling met [naam]", location="Zaal [naam]"))
    activity = _activity(db_session, description="Vraag het aan Zebedeus Quackenbosch.")

    proposal = _propose(db_session, activity, request="In zaal Quackenbosch, zegt Zebedeus.")

    sent = provider.payloads()
    assert "quackenbosch" not in sent and "zebedeus" not in sent
    assert "[naam]" in sent
    assert proposal.fields == [], "a value with a removed name in it is not proposed"
    assert len(proposal.left_out) == 2


def test_the_system_prompt_carries_no_stored_content(db_session, raakje):
    """The proof `SCAN_PROMPT_NAMES = False` asks for: the system message is the
    module's constant, whatever the record and the request hold."""
    provider = raakje(_answer(description="Kom mee."), _verdict())
    activity = _activity(db_session, name="Uniekenaamwandeling", location="Kerkplein")
    _propose(db_session, activity)
    assert proposer.SCAN_PROMPT_NAMES is False
    systems = [m["content"] for call in provider.asked for m in call if m["role"] == "system"]
    assert systems == [proposer.SYSTEM_PROMPT, proposer.VERIFY_PROMPT]
    assert "Uniekenaamwandeling" not in "".join(systems) and "Kerkplein" not in "".join(systems)
    assert "2026-10-05" in provider.asked[0][1]["content"], "today stands in the user message"


# ── The route and the panel ──────────────────────────────────────────────────


def _login(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value), "HX-Request": "true"}


def _switch(db, monkeypatch, on: bool) -> None:
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr("app.config.settings.admin_chat_enabled", on)
    set_setting(db, "admin_chat_enabled", "1" if on else None)
    db.commit()


def _fields_of(html: str) -> list[dict]:
    found = re.search(
        r"<script type=\"application/json\" data-proposal-fields>(.*?)</script>", html, re.S
    )
    return json.loads(found.group(1))


def test_the_panel_asks_and_gets_one_turn_that_writes_nothing(
    client, db_session, monkeypatch, raakje
):
    headers = _login(client)
    _switch(db_session, monkeypatch, True)
    activity = _activity(db_session)
    db_session.commit()
    raakje(
        _answer(**(FULL | {"description": FULL["description"] + " Er is een tombola."})),
        _verdict((3, "staat niet in de vraag")),
    )

    answer = client.post(
        f"/admin/activiteiten/{activity.id}/raakje/voorstel",
        headers=headers,
        data={"vraag": REQUEST},
    )

    assert answer.status_code == 200 and "X-Raakje-Failed" not in answer.headers
    html = answer.text
    assert "data-form-flow" not in html and "<html" not in html, "a turn, no page"
    assert REQUEST in html and "Voorstel klaar." in html
    block = re.search(r"<form data-form-proposal[^>]*>", html).group(0)
    assert "data-proposal-apply-url" not in block, "Toepassen sends nothing: it applies in the page"
    assert "data-proposal-auto" not in block
    assert "5 velden ingevuld als voorstel" in html
    assert [f["name"] for f in _fields_of(html)] == [
        "name",
        "location",
        "description",
        "start_date",
        "start_time",
    ]
    assert "zaterdag 14 november 2026" in html, "the panel reads the date in words"
    tick = re.search(r'<input type="checkbox" name="keep"[^>]*>', html).group(0)
    assert 'value="3"' in tick and "checked" not in tick, "left out unless it is ticked"
    assert "«Er is een tombola.»" in html and "wordt weggelaten" in html

    db_session.expire_all()
    stored = db_session.get(Activity, activity.id)
    assert (stored.name, stored.location, stored.description) == ("Wandeling", None, None)
    assert stored.dates == [], "the proposal wrote no date"


def test_what_was_not_proposed_stands_in_the_turn(client, db_session, monkeypatch, raakje):
    headers = _login(client)
    _switch(db_session, monkeypatch, True)
    activity = _activity(db_session)
    db_session.commit()
    raakje(_answer(location="Gemeentehuis Wommelgem"))

    answer = client.post(
        f"/admin/activiteiten/{activity.id}/raakje/voorstel",
        headers=headers,
        data={"vraag": "Waar is het?"},
    )

    assert "data-proposal-left-out" in answer.text
    assert "Locatie: niet voorgesteld" in answer.text
    assert "data-form-proposal" not in answer.text, "nothing to apply, so no block"


def test_a_failed_answer_keeps_the_question(client, db_session, monkeypatch, raakje):
    headers = _login(client)
    _switch(db_session, monkeypatch, True)
    activity = _activity(db_session)
    db_session.commit()
    raakje("Geen JSON.")
    answer = client.post(
        f"/admin/activiteiten/{activity.id}/raakje/voorstel",
        headers=headers,
        data={"vraag": "Schrijf een omschrijving."},
    )
    assert answer.headers["X-Raakje-Failed"] == "1"
    assert "data-turn-failed" in answer.text and "geen bruikbaar voorstel" in answer.text


def test_switched_off_there_is_no_proposer(client, db_session, monkeypatch, raakje):
    headers = _login(client)
    activity = _activity(db_session)
    db_session.commit()
    provider = raakje(_answer(name="X"))
    url = f"/admin/activiteiten/{activity.id}/raakje/voorstel"

    _switch(db_session, monkeypatch, False)
    assert client.post(url, headers=headers, data={"vraag": "x"}).status_code == 404
    # the tenant's switch alone is not enough: the environment decides first
    from app.kernel.tenant_config import set_setting

    set_setting(db_session, "admin_chat_enabled", "1")
    db_session.commit()
    assert client.post(url, headers=headers, data={"vraag": "x"}).status_code == 404
    assert provider.asked == [], "no call left"

    _switch(db_session, monkeypatch, True)
    assert client.post(url, headers=headers, data={"vraag": "x"}).status_code == 200
    missing = client.post(
        "/admin/activiteiten/999999/raakje/voorstel", headers=headers, data={"vraag": "x"}
    )
    assert missing.status_code == 404


def test_the_call_is_registered_under_a_capability_of_its_own(db_session, raakje, monkeypatch):
    """The same gate and cost registration as the newsletter's proposer: what
    the sink is handed carries `activity_drafting`, a code the list knows."""
    from app.domains.chatbot import api as chatbot
    from app.domains.chatbot.codes import AI_CAPABILITY_CODES

    seen = []
    real = chatbot.admin_rules

    def rules(names, *, capability, scan_prompt_names=True):
        seen.append(capability)
        return real(names, capability=capability, scan_prompt_names=scan_prompt_names)

    monkeypatch.setattr("app.domains.chatbot.api.admin_rules", rules)
    raakje(_answer(name="Herfstwandeling"))
    _propose(db_session, _activity(db_session))
    assert seen == [chatbot.AiCapability.ACTIVITY_DRAFTING]
    assert "activity_drafting" in {seed.code for seed in AI_CAPABILITY_CODES}


def test_the_panel_proposes_while_the_fiche_is_edited_and_answers_while_it_reads(db_session):
    activity = _activity(db_session, name="Herfstwandeling")
    base = f"http://testserver/admin/activiteiten/{activity.id}"

    reading = context_for(db_session, base, tenant_id=1)
    editing = context_for(db_session, base + "?bewerken=1", tenant_id=1)
    tab = context_for(db_session, base + "/inschrijvingen?bewerken=1", tenant_id=1)

    assert reading.key == f"activity:{activity.id}"
    assert reading.post_url == f"/admin/rapporten/raakje/activiteit/{activity.id}"
    assert editing.key == f"activity-edit:{activity.id}", "another key, so the panel swaps"
    assert editing.post_url == f"/admin/activiteiten/{activity.id}/raakje/voorstel"
    assert editing.label == "voorstel voor Herfstwandeling" and editing.can_ask
    assert tab.key == reading.key, "only the fiche has an edit state"
