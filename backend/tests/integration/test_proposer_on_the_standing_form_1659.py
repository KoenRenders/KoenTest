"""A second request to Raakje builds on the form as it stands (#1659).

Koen's case on HDEV (6 October 2026): a first proposal applied on a new
activity — name, location, description and the hours — and then a second
request for the day. The proposer read the STORED record, which for a new
activity holds nothing: it did not know the hours were there, and every field
it proposed again had the stored value as its base, so Toepassen skipped it as
"changed meanwhile".

The panel now sends the fiche's form along and the proposer takes it as the
record. No model: every answer is scripted.

Broken on purpose (6 October 2026), each red for its own reason:

- the facade dropping the form → the hours of the form are no source ("Van
  (10:00): niet voorgesteld") and the name's base is the stored one;
- the first row of the form not taken as the row → the day comes with the
  hours as new fields, and the bases of an unchanged form are empty;
- the form's values taken off the panel's edit context → the context test;
- a row without a day left out of the record's text → the model is not told
  the hours stand there;
- the line for a missing day on a row of the form taken out → the panel is
  silent about it.
"""

from __future__ import annotations

import json
import re
from datetime import date, time

import pytest

from app.domains.activities.api import Activity, ActivityDate, proposal_vals
from app.domains.activities.fiche_form import proposal_fields
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.chatbot.providers.base import AssistantMessage
from app.domains.reporting.assistant_context import context_for
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

NEW = "/admin/activiteiten/nieuw"
DAY = "Het is op vrijdag 11 december."
#: The form after the first proposal was applied: three texts, and one date
#: row that carries the hours and no day yet.
APPLIED = {
    "name": "Schaatsen",
    "location": "schaatsbaan",
    "description": "Kom mee schaatsen.",
    "d_order": ["n1"],
    "d.n1.start_date": "",
    "d.n1.end_date": "",
    "d.n1.start_time": "10:00",
    "d.n1.end_time": "12:00",
}


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
def raakje(client, db_session, monkeypatch):
    """The panel's proposer switched on, with a scripted model; returns
    `ask(path, data, *answers)` → (fields, html, what the model was sent)."""
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr("app.config.settings.admin_chat_enabled", True)
    set_setting(db_session, "admin_chat_enabled", "1")
    db_session.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    headers = {"X-CSRF-Token": csrf_token_for(value), "HX-Request": "true"}

    def ask(path: str, data: dict, *answers: str):
        provider = Scripted(*answers)
        monkeypatch.setattr("app.domains.chatbot.api.get_provider", lambda model="": provider)
        answer = client.post(f"{path}/raakje/voorstel", headers=headers, data=data)
        assert answer.status_code == 200, answer.text[:300]
        found = re.search(
            r"<script type=\"application/json\" data-proposal-fields>(.*?)</script>",
            answer.text,
            re.S,
        )
        return (json.loads(found.group(1)) if found else []), answer.text, provider.asked

    return ask


def _answer(**fields) -> str:
    return json.dumps({"reply": "Voorstel klaar.", **fields}, ensure_ascii=False)


#: What a model that was shown the standing form answers to "add the day": it
#: repeats what stands there and adds the day.
WITH_DAY = _answer(
    name="Schaatsen",
    location="schaatsbaan",
    date={"start_date": "2026-12-11", "start_time": "10:00", "end_time": "12:00"},
    date_source="vrijdag 11 december",
)


def test_the_day_of_the_second_request_comes_on_the_row_that_carries_the_hours(raakje):
    """Koen's case. Red on master: the hours of the form are no source there,
    so they are refused by name, and nothing says the row exists."""
    fields, html, asked = raakje(NEW, {"vraag": DAY} | APPLIED, WITH_DAY)

    assert [(f["name"], f.get("group"), f["value"], f["base"]) for f in fields] == [
        ("start_date", "d_order", "2026-12-11", "")
    ], "only the day is new: the name, the place and the hours stand in the form already"
    assert "niet voorgesteld" not in html, "the hours of the form are a source"
    assert "De dag ontbreekt nog" not in html
    # the model was shown the form, not the empty stored record
    assert "Naam: Schaatsen" in asked[0] and "Locatie: schaatsbaan" in asked[0]
    assert "(dag nog niet ingevuld), 10:00–12:00" in asked[0]


def test_without_the_form_the_request_reads_the_stored_record_as_before(raakje):
    """The same answer for a caller that sends the question alone: the stored
    (empty) record is the source, so the hours nobody gave are refused."""
    fields, html, asked = raakje(NEW, {"vraag": DAY}, WITH_DAY)

    assert "Naam: \\n" in asked[0] and "Datums: (geen)" in asked[0]
    assert "Van (10:00): niet voorgesteld" in html and "Tot (12:00): niet voorgesteld" in html
    assert {f["name"] for f in fields} == {"name", "start_date"}


def test_on_an_existing_activity_the_unsaved_value_is_the_base_and_nothing_is_written(
    raakje, db_session
):
    """A name typed (or applied) and not saved is the record's name for the next
    request: proposed again it is nothing new, changed it has the FORM's value
    as its base — the stored one would make Toepassen skip it."""
    activity = Activity(name="Wandeling")
    db_session.add(activity)
    db_session.flush()
    row = ActivityDate(
        activity_id=activity.id, start_date=date(2026, 11, 14), start_time=time(14, 0)
    )
    db_session.add(row)
    db_session.commit()
    form = {
        "name": "Herfstwandeling",
        "location": "",
        "description": "",
        "d_order": [str(row.id)],
        f"d.{row.id}.start_date": "2026-11-14",
        f"d.{row.id}.start_time": "14:00",
    }
    path = f"/admin/activiteiten/{activity.id}"

    same, _html, asked = raakje(
        path, {"vraag": "Laat de naam zoals hij is."} | form, _answer(name="Herfstwandeling")
    )
    assert same == [], "what the form holds already is not proposed again"
    assert "Naam: Herfstwandeling" in asked[0] and "Naam: Wandeling" not in asked[0]

    changed, _html, _asked = raakje(
        path, {"vraag": "Noem het Herfsttocht."} | form, _answer(name="Herfsttocht")
    )
    assert [(f["name"], f["value"], f["base"]) for f in changed] == [
        ("name", "Herfsttocht", "Herfstwandeling")
    ]

    db_session.expire_all()
    stored = db_session.get(Activity, activity.id)
    assert stored.name == "Wandeling", "a request for a proposal stores nothing of the form"
    assert [(d.start_date, d.start_time) for d in stored.dates] == [(date(2026, 11, 14), time(14))]


def test_a_first_request_on_a_form_nobody_changed_is_the_request_of_before(raakje, db_session):
    """The form sent along equals the stored record: the model is sent the same
    text, letter for letter, and the proposal is the same."""
    activity = Activity(name="Wandeling", location="Parochiezaal", description="Kom mee.")
    db_session.add(activity)
    db_session.flush()
    late = ActivityDate(activity_id=activity.id, start_date=date(2026, 11, 21))
    early = ActivityDate(
        activity_id=activity.id,
        start_date=date(2026, 11, 14),
        start_time=time(14, 0),
        end_time=time(16, 0),
    )
    db_session.add_all([late, early])
    db_session.commit()
    form = {
        "name": "Wandeling",
        "location": "Parochiezaal",
        "description": "Kom mee.",
        # the order of the screen: earliest first
        "d_order": [str(early.id), str(late.id)],
        f"d.{early.id}.start_date": "2026-11-14",
        f"d.{early.id}.start_time": "14:00",
        f"d.{early.id}.end_time": "16:00",
        f"d.{late.id}.start_date": "2026-11-21",
    }
    path = f"/admin/activiteiten/{activity.id}"
    request = {"vraag": "Het begint om 15 uur."}
    answer = _answer(name="Herfstwandeling", date={"start_time": "15:00"})

    alone = raakje(path, request, answer)
    with_form = raakje(path, request | form, answer)

    assert with_form[2] == alone[2], "the model is sent the same sources"
    assert with_form[0] == alone[0] and len(alone[0]) == 2
    assert {f["name"]: f["base"] for f in alone[0]} == {"name": "Wandeling", "start_time": "14:00"}


def test_hours_on_a_row_of_the_form_without_a_day_say_the_day_is_missing(raakje):
    """The new fiche opens with one empty date row: the hours go on it (no new
    row), and the panel says the day is still the user's to give."""
    empty_row = {"name": "", "location": "", "description": "", "d_order": ["n1"]}
    fields, html, asked = raakje(
        NEW,
        {"vraag": "Schaatsen van 10 tot 12 uur."} | empty_row,
        _answer(name="Schaatsen", date={"start_time": "10:00", "end_time": "12:00"}),
    )

    assert [(f["name"], f.get("group")) for f in fields] == [
        ("name", None),
        ("start_time", "d_order"),
        ("end_time", "d_order"),
    ]
    assert "De dag ontbreekt nog: vul de datum zelf in." in html
    assert "nieuwe datumrij" not in html, "the row is there already"
    assert "Datums: (geen)" in asked[0], "a row nobody filled in says nothing"


def test_the_panel_sends_the_form_along_in_both_edit_contexts(db_session):
    activity = Activity(name="Wandeling")
    db_session.add(activity)
    db_session.commit()
    new = context_for(db_session, f"http://testserver{NEW}", tenant_id=1)
    edit = context_for(
        db_session, f"http://testserver/admin/activiteiten/{activity.id}?bewerken=1", tenant_id=1
    )
    read = context_for(
        db_session, f"http://testserver/admin/activiteiten/{activity.id}", tenant_id=1
    )

    assert new.vals == edit.vals == proposal_vals() != ""
    assert read.vals == "", "reading, the panel answers questions: there is no form"
    assert new.vals == (
        'js:{...window.raakRecordForm.valuesOf(["name", "location", "description", "d_order"], ["d."])}'
    )
    # Not as included fields: htmx validates those, and a date row without its
    # required day stops the request (the e2e measures it in the browser).
    assert new.include == edit.include == ""


def test_a_request_without_the_form_is_read_as_one():
    from starlette.datastructures import FormData

    assert proposal_fields(FormData([("vraag", "Schrijf een omschrijving.")])) is None
    texts, rows = proposal_fields(
        FormData([("name", " Wandeling "), ("d_order", "7"), ("d.7.start_date", "geen datum")])
    )
    assert texts == {"name": "Wandeling", "location": "", "description": ""}
    assert [(r.key, r.start_date, r.start_time) for r in rows] == [("7", None, None)]
