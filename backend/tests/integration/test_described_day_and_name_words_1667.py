"""An ordinal is no name, a described day is worked out, a turn always says something (#1667).

Koen on HDEV, 6 October 2026: he asked for an evening market "op de derde
laatste vrijdag van december". Raakje proposed 25 December, the LAST Friday,
and his correction changed nothing. Measured in the AI call log: the model had
been sent "de [naam] laatste vrijdag van december" — somebody's name there
holds "derde", and the scrubber took the ordinal for it. His second request
then got a turn with nothing in it: his own question and no word under it.

No model: every answer is scripted, and the real guard still wraps the stand-in.

Broken on purpose (6 October 2026), each red for its own reason:

- the ordinary words taken out of `name_parts` → "derde" is a name part again
  and the model is sent "[naam]";
- the newsletter's scrubber given its own copy of the rule that removes any
  word → the two scrubbers answer differently;
- the described day not used in `_date_fields` → the model's 25 December is
  proposed and no sum is shown;
- "laatste" read from the front → 4 December;
- the check for a turn that says nothing taken out → the route answers 200
  with the question alone;
- the sum not rendered in the turn → the correction test finds no line.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from app.domains.activities import proposer
from app.domains.activities.api import Activity
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.chatbot.providers.base import AssistantMessage
from app.domains.mdm.api import Person, name_parts, person_name_parts
from app.domains.newsletter import drafting
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

TODAY = date(2026, 10, 5)
MARKET = "Een avondmarkt op de derde laatste vrijdag van december, dit jaar, van 18 tot 22 uur."
CORRECTION = "We bedoelden de derde laatste vrijdag van december. Dat is dus niet 25 december."
SUM = "Uitgerekend: derde laatste vrijdag van december = vrijdag 11 december 2026."


class Scripted:
    name, model = "mock", "scripted"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked: list[str] = []

    def complete(self, messages, tools=None, tool_choice=None):
        self.asked.append(json.dumps(messages, ensure_ascii=False))
        return AssistantMessage(
            content=self.answers.pop(0) if self.answers else json.dumps({"unsupported": []})
        )


@pytest.fixture
def raakje(monkeypatch):
    def install(*answers):
        provider = Scripted(*answers)
        monkeypatch.setattr("app.domains.chatbot.api.get_provider", lambda model="": provider)
        return provider

    return install


def _answer(**fields) -> str:
    return json.dumps(fields, ensure_ascii=False)


def _propose(db, request, activity=None):
    return proposer.propose(
        db, activity or Activity(name=""), request=request, actor="s@example.org", today=TODAY
    )


# ── The words of the calendar and of counting are no names ──────────────────


def test_an_ordinal_a_weekday_and_a_month_are_no_name_parts():
    """Red on master: {"derde", "mei", "zondag"} were parts like any other."""
    parts = name_parts(["Jan de Derde", "Mei Peeters", "Zondag", "Laatste", "Zebedeus"])
    assert parts == {"jan", "peeters", "zebedeus"}


@pytest.mark.parametrize("scrub", [proposer.scrub, drafting.scrub])
def test_the_described_day_passes_the_scrubber_and_a_name_still_goes(scrub):
    """Both doors — the activity's proposer and the newsletter's writer — and
    since #1667 one rule behind them."""
    names = name_parts(["Jan de Derde", "Zebedeus Quackenbosch"])
    text = "Zebedeus vraagt de derde laatste vrijdag van december, schrijf naar z@example.org."
    assert scrub(text, names) == (
        "[naam] vraagt de derde laatste vrijdag van december, schrijf naar [e-mailadres]."
    )


@pytest.mark.parametrize(
    "text",
    [
        "Quackenbosch komt op de eerste maandag van mei.",
        "ZEBEDEUS en quackenbosch-janssens, 'Zebedeus'",
        "Geen naam hier, alleen een zin over zondag.",
        "",
    ],
)
def test_the_two_scrubbers_are_one(text):
    names = name_parts(["Zebedeus Quackenbosch"])
    assert proposer.scrub(text, names) == drafting.scrub(text, names)


def test_with_someone_called_derde_the_model_still_reads_the_ordinal(db_session, raakje):
    """The measured case, end to end: the name is in the administration, the
    request reaches the model with its ordinal, and the guard lets it through.
    The person's own name still does not leave."""
    db_session.add(Person(first_name="Zebedeus", last_name="De Derde"))
    db_session.flush()
    assert person_name_parts(db_session) >= {"zebedeus"}
    assert "derde" not in person_name_parts(db_session)
    provider = raakje(_answer(reply="Voorstel klaar.", name="Avondmarkt"))

    _propose(db_session, MARKET + " Vraag het aan Zebedeus.")

    sent = provider.asked[0]
    assert "de derde laatste vrijdag van december" in sent
    assert "zebedeus" not in sent.lower() and "[naam]" in sent


# ── A described day is worked out here, not by the model ────────────────────


@pytest.mark.parametrize(
    ("text", "day"),
    [
        ("op de derde laatste vrijdag van december", date(2026, 12, 11)),
        ("de laatste vrijdag van december", date(2026, 12, 25)),
        ("de eerste maandag van november", date(2026, 11, 2)),
        ("De  Derde   Laatste Vrijdag van December", date(2026, 12, 11)),
        # May has passed on 5 October: the first such day from today on.
        ("de voorlaatste zondag in mei", date(2027, 5, 23)),
        ("de voorlaatste zondag in mei, dit jaar", date(2026, 5, 24)),
        ("de tweede dinsdag in maart 2027", date(2027, 3, 9)),
        # February 2027 has four Fridays.
        ("de vijfde vrijdag van februari 2027", None),
        # A weekday in a month fixes no day.
        ("een vrijdag in december", None),
        ("zaterdag 14 november om 14 uur", None),
    ],
)
def test_a_day_described_by_its_place_in_the_month(text, day):
    found = proposer.described_day(text, TODAY)
    assert (found[0] if found else None) == day


def test_the_described_day_wins_from_the_day_the_model_made_of_it(db_session, raakje):
    """Red on master: 25 December, the last Friday, as the model read it."""
    raakje(
        _answer(
            reply="Voorstel klaar.",
            name="Avondmarkt",
            date={"start_date": "2026-12-25", "start_time": "18:00", "end_time": "22:00"},
            date_source="laatste vrijdag van december",
        )
    )
    proposal = _propose(db_session, MARKET)

    fields = {f["name"]: f for f in proposal.fields}
    assert fields["start_date"]["value"] == "2026-12-11"
    assert fields["start_date"]["shown"] == "vrijdag 11 december 2026"
    assert (fields["start_time"]["value"], fields["end_time"]["value"]) == ("18:00", "22:00")
    assert {f["group"] for f in proposal.fields if f["name"] != "name"} == {"d_order"}, (
        "the date names the group — its first row — and no other row"
    )
    assert proposal.notes == [SUM], "the sum the user can check before Toepassen"
    assert proposal.left_out == []


def test_the_described_day_is_proposed_also_when_the_model_proposed_none(db_session, raakje):
    raakje(_answer(reply="Welke datum bedoel je?"))
    proposal = _propose(db_session, MARKET)
    assert [(f["name"], f["value"]) for f in proposal.fields] == [("start_date", "2026-12-11")]
    assert proposal.notes == [SUM]


def test_a_day_nobody_gave_or_described_is_still_not_proposed(db_session, raakje):
    raakje(
        _answer(
            reply="Voorstel klaar.",
            date={"start_date": "2026-12-11"},
            date_source="ergens rond de feestdagen",
        )
    )
    proposal = _propose(db_session, "Een avondmarkt, ergens rond de feestdagen.")
    assert proposal.fields == [] and proposal.notes == []
    assert any(line.startswith("Datum (vrijdag 11 december 2026)") for line in proposal.left_out)


# ── The route: a correction on the standing form, and a turn that says something ──


@pytest.fixture
def ask(client, db_session, monkeypatch):
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr("app.config.settings.admin_chat_enabled", True)
    set_setting(db_session, "admin_chat_enabled", "1")
    db_session.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    headers = {"X-CSRF-Token": csrf_token_for(value), "HX-Request": "true"}

    def post(data: dict, *answers: str):
        provider = Scripted(*answers)
        monkeypatch.setattr("app.domains.chatbot.api.get_provider", lambda model="": provider)
        return client.post("/admin/activiteiten/nieuw/raakje/voorstel", headers=headers, data=data)

    return post


#: The form after the first, wrong proposal was applied (#1659 sends it along).
APPLIED = {
    "name": "Avondmarkt",
    "location": "",
    "description": "",
    "d_order": ["n1"],
    "d.n1.start_date": "2026-12-25",
    "d.n1.start_time": "18:00",
    "d.n1.end_time": "22:00",
}


def _fields(html: str) -> list[dict]:
    found = re.search(
        r"<script type=\"application/json\" data-proposal-fields>(.*?)</script>", html, re.S
    )
    return json.loads(found.group(1)) if found else []


def test_the_correction_moves_the_day_on_the_row_that_stands(ask):
    """Koen's second request, with the model answering as it did on HDEV: a
    reply and no field. The day is corrected all the same, on the first row,
    with the 25th as its base. The year is named: the route reads the real
    date, and without a year the answer would change after 11 December."""
    answer = ask(
        {"vraag": CORRECTION.replace("december.", "december 2026.")} | APPLIED,
        _answer(reply="Geef de correcte datum van de laatste vrijdag van december 2026."),
    )

    assert answer.status_code == 200 and "X-Raakje-Failed" not in answer.headers
    assert [(f["name"], f.get("group"), f["value"], f["base"]) for f in _fields(answer.text)] == [
        ("start_date", "d_order", "2026-12-11", "2026-12-25")
    ]
    notes = re.search(r"<ul data-proposal-notes[^>]*>(.*?)</ul>", answer.text, re.S).group(1)
    assert SUM.replace("december =", "december 2026 =") in notes


def test_an_answer_with_only_a_reply_is_the_turns_text(ask):
    answer = ask({"vraag": "Wat heb je nog nodig?"}, _answer(reply="Zeg me waar het doorgaat."))

    assert answer.status_code == 200 and "X-Raakje-Failed" not in answer.headers
    assert "data-turn-failed" not in answer.text
    said = re.search(r"<div data-raakje-answer[^>]*>(.*?)</div>", answer.text, re.S).group(1)
    assert said.strip() == "Zeg me waar het doorgaat."
    assert "data-form-proposal" not in answer.text


@pytest.mark.parametrize(
    "content", ["{}", '{"reply": ""}', '{"reply": "  ", "name": ""}', "geen json"]
)
def test_an_answer_that_says_nothing_is_the_error_sentence_and_keeps_the_question(ask, content):
    """Red on master for the first three: a turn with the question alone, and
    the field emptied as if it had been answered."""
    answer = ask({"vraag": "Wat heb je nog nodig?"}, content)

    assert answer.status_code == 200
    assert answer.headers.get("X-Raakje-Failed") == "1", "the panel must keep the question"
    assert "data-turn-failed" in answer.text
    said = re.search(r"<div data-raakje-answer[^>]*>(.*?)</div>", answer.text, re.S)
    assert said is not None and said.group(1).strip() != "", "the turn says nothing"
