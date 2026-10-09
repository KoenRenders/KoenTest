"""The form builder says why it refuses a question or an option without a label (#1831).

The builder is one page with a form per question and a row per option. A
refusal of its service was answered as a bare JSON 422 — the sentence inside
it, the page showing the kit's general message. And an EMPTY label did not even
get that far: the routes required the field.

Three doors answer the kit's refusal into the message line of THEIR form — a new
question, a new option, a changed option — read here as the screen gets it
(`tests/_refusal.py`), with the line it is sent to found once in the builder
the board is looking at, and nothing written.

The fourth, a CHANGED question, already said why in its own way (#1136): the
builder again with the reason in its banner. That stays; only an empty label
did not reach it.

A changed option without a label was no refusal in the service at all: it kept
its old label without a word and wrote the rest. It is refused now, by the same
rule as a new option.

Red proofs, one replacement each, the tree as before afterwards — the counts
stand in the pull request.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.models import FormField, FormFieldOption, FormSection
from tests import forms_door
from tests._refusal import heading, message_line, page_banner, said
from tests.conftest import SEEDED_ADMIN_EMAIL

QUESTION_RULE = "Elk veld heeft een vraag/label nodig."
OPTION_RULE = "Elke optie heeft een label nodig."
EMPTY = pytest.mark.parametrize(
    "label", [None, "", "   "], ids=["no label field", "an empty label", "a label of spaces"]
)


def _board(client) -> dict[str, str]:
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


def _given(label, **more) -> dict:
    return more if label is None else {"label": label, **more}


def _new_form(client) -> tuple[dict, str, int]:
    headers = _board(client)
    form_id = forms_door.create_form(client, {"title": "Wandeling", "sections": []}).json()["id"]
    return headers, f"/admin/formulieren/{form_id}", form_id


@pytest.fixture
def builder(client, db_session):
    """A form with one section, holding one choice question with one option."""
    headers, base, form_id = _new_form(client)
    assert (
        client.post(f"{base}/secties", data={"title": "Vooraf"}, headers=headers).status_code == 200
    )
    db_session.expire_all()
    section = db_session.query(FormSection).filter_by(form_id=form_id).one()
    made = client.post(
        f"{base}/velden",
        data={"label": "Welke afstand?", "field_type": "radio", "section_id": str(section.id)},
        headers=headers,
    )
    assert made.status_code == 200, made.text[:200]
    db_session.expire_all()
    field = db_session.query(FormField).filter(FormField.form_id == form_id).one()
    assert field.section_id == section.id
    made = client.post(f"{base}/velden/{field.id}/opties", data={"label": "5 km"}, headers=headers)
    assert made.status_code == 200, made.text[:200]
    db_session.expire_all()
    option = db_session.query(FormFieldOption).filter_by(field_id=field.id).one()
    return {
        "headers": headers,
        "base": base,
        "form_id": form_id,
        "field_id": field.id,
        "section_id": section.id,
        "option_id": option.id,
    }


def _refused_in(client, base: str, answer, rule: str, line: str) -> None:
    """The kit's refusal with the rule's sentence, sent to `line` — and that line
    stands once in the builder the board has on the screen."""
    assert answer.status_code == 422
    assert heading(answer) == "Opslaan is niet gelukt."
    assert said(answer) == [rule]
    assert message_line(answer) == line
    page = client.get(base, headers={"HX-Request": "true"}).text
    assert page.count(f'id="{line.lstrip("#")}"') == 1, f"the builder has no line {line}"


def _stored(db, builder) -> tuple:
    db.expire_all()
    fields = db.query(FormField).filter(FormField.form_id == builder["form_id"]).all()
    options = db.query(FormFieldOption).filter_by(field_id=builder["field_id"]).all()
    return (
        sorted((f.id, f.label, f.help_text) for f in fields),
        sorted((o.id, o.label, o.is_other) for o in options),
    )


@EMPTY
def test_a_new_question_without_a_label_says_why_in_its_form(client, db_session, builder, label):
    before = _stored(db_session, builder)
    section = builder["section_id"]

    answer = client.post(
        f"{builder['base']}/velden",
        data=_given(label, field_type="text", section_id=str(section)),
        headers=builder["headers"],
    )

    _refused_in(client, builder["base"], answer, QUESTION_RULE, f"#fb-veld-nieuw-{section}-melding")
    assert _stored(db_session, builder) == before


def test_the_first_question_of_an_empty_form_says_why_too(client, db_session):
    """An empty form has no section yet: its one new-question form carries the
    line without a section in its name."""
    headers, base, form_id = _new_form(client)

    answer = client.post(
        f"{base}/velden", data={"label": " ", "field_type": "text"}, headers=headers
    )

    _refused_in(client, base, answer, QUESTION_RULE, "#fb-veld-nieuw--melding")
    db_session.expire_all()
    assert db_session.query(FormField).filter(FormField.form_id == form_id).count() == 0


@EMPTY
def test_a_new_option_without_a_label_says_why_in_its_row(client, db_session, builder, label):
    before = _stored(db_session, builder)
    field = builder["field_id"]

    answer = client.post(
        f"{builder['base']}/velden/{field}/opties",
        data=_given(label, is_other="1"),
        headers=builder["headers"],
    )

    _refused_in(client, builder["base"], answer, OPTION_RULE, f"#fb-optie-nieuw-{field}-melding")
    assert _stored(db_session, builder) == before


@EMPTY
def test_an_option_that_loses_its_label_says_why_in_its_row(client, db_session, builder, label):
    """It kept its old label without a word and wrote the rest ("Andere…" ticked)."""
    before = _stored(db_session, builder)
    option = builder["option_id"]

    answer = client.post(
        f"{builder['base']}/opties/{option}",
        data=_given(label, is_other="1"),
        headers=builder["headers"],
    )

    _refused_in(client, builder["base"], answer, OPTION_RULE, f"#fb-optie-{option}-melding")
    assert _stored(db_session, builder) == before


@EMPTY
def test_a_question_that_loses_its_label_says_why_in_the_builders_banner(
    client, db_session, builder, label
):
    """This door's own way, since #1136: the builder again, the reason in its banner."""
    before = _stored(db_session, builder)

    answer = client.post(
        f"{builder['base']}/velden/{builder['field_id']}",
        data=_given(label, field_type="radio", help_text="Kies er één."),
        headers=builder["headers"],
    )

    assert answer.status_code == 200
    assert page_banner(answer) == QUESTION_RULE
    assert _stored(db_session, builder) == before, "the rest of the refused change was written"


def test_a_good_save_answers_the_builder_with_empty_lines(client, db_session, builder):
    option = builder["option_id"]

    answer = client.post(
        f"{builder['base']}/opties/{option}", data={"label": "10 km"}, headers=builder["headers"]
    )

    assert answer.status_code == 200
    assert "data-save-refusal" not in answer.text
    assert f'id="fb-optie-{option}-melding"' in answer.text
    db_session.expire_all()
    assert db_session.get(FormFieldOption, option).label == "10 km"


def test_an_option_that_is_not_there_stays_a_404(client, builder):
    answer = client.post(
        f"{builder['base']}/opties/999999", data={"label": "20 km"}, headers=builder["headers"]
    )

    assert answer.status_code == 404
