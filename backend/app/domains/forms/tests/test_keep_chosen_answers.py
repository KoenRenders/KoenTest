"""A chosen option or an answered question cannot be removed (#1347).

Koen, 29 September 2026: deleting an answer option in the form builder silently
wiped the answer of everyone who chose it. `value_option_id` was `SET NULL`, so the
answer stayed as an empty row that read as "did not answer"; a question's answers
went with `CASCADE`. On PROD it cost one answer that day.

Every way in meets the same rule, `refuse_losing_answers`: the two delete buttons
of the builder, and `apply_definition`, which the JSON API runs. The database is
the net under it: `RESTRICT` on `value_option_id` since migration 175.

Proven red against master `3bfd3506`, this file copied onto an export of it. Four of
seven failed:
- deleting the chosen option and the answered question: no reason on the screen,
  and both were gone;
- a direct DELETE of the chosen option: no `IntegrityError` (it was SET NULL);
- the JSON API dropping the chosen option: 200 instead of 422.
The other three pass on master as they must: an option nobody chose and an
unanswered question stay removable, and deleting a whole form keeps working.
"""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.models import (
    Form,
    FormField,
    FormFieldOption,
    FormSubmission,
    FormSubmissionAnswer,
)
from tests import forms_door
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

REFUSED_OPTION = "1 inzending(en) kozen dit antwoord. Verwijderen zou hun antwoord wissen."
REFUSED_FIELD = "1 inzending(en) beantwoordden deze vraag. Verwijderen zou hun antwoord wissen."


def _login(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _form(db):
    """A radio question "Welke dag?" with two options; one submission chose "Zaterdag".
    A second, unanswered question "Opmerking"."""
    tag = secrets.token_hex(3)
    form = Form(title="Dagkeuze", slug=f"dagkeuze-{tag}", status="open", share_token=f"t-{tag}")
    db.add(form)
    db.flush()
    day = FormField(form_id=form.id, label="Welke dag?", field_type="radio", position=0)
    note = FormField(form_id=form.id, label="Opmerking", field_type="text", position=1)
    db.add_all([day, note])
    db.flush()
    saturday = FormFieldOption(field_id=day.id, label="Zaterdag", position=0)
    sunday = FormFieldOption(field_id=day.id, label="Zondag", position=1)
    db.add_all([saturday, sunday])
    db.flush()
    submission = FormSubmission(form_id=form.id)
    db.add(submission)
    db.flush()
    db.add(
        FormSubmissionAnswer(
            submission_id=submission.id, field_id=day.id, value_option_id=saturday.id
        )
    )
    db.commit()
    return form, day, note, saturday, sunday


def _answer(db, option_id):
    return db.query(FormSubmissionAnswer).filter_by(value_option_id=option_id).one_or_none()


def test_a_chosen_option_is_refused_with_the_reason_on_the_screen(client, db_session):
    form, _day, _note, saturday, _sunday = _form(db_session)
    headers = _login(client)

    answer = client.post(
        f"/admin/formulieren/{form.id}/opties/{saturday.id}/verwijderen", headers=headers
    )

    assert answer.status_code == 200, answer.text[:200]
    assert REFUSED_OPTION in answer.text, "the builder says why"
    db_session.expire_all()
    assert db_session.get(FormFieldOption, saturday.id) is not None, "the option is still there"
    assert _answer(db_session, saturday.id) is not None, "the answer still points at it"


def test_an_option_nobody_chose_is_removed(client, db_session):
    form, _day, _note, _saturday, sunday = _form(db_session)
    headers = _login(client)

    answer = client.post(
        f"/admin/formulieren/{form.id}/opties/{sunday.id}/verwijderen", headers=headers
    )

    assert answer.status_code == 200
    assert "kozen dit antwoord" not in answer.text
    db_session.expire_all()
    assert db_session.get(FormFieldOption, sunday.id) is None


def test_the_database_refuses_deleting_a_chosen_option(db_session):
    _form_, _day, _note, saturday, _sunday = _form(db_session)
    with pytest.raises(IntegrityError, match="form_submission_answers_value_option_id_fkey"):
        db_session.execute(
            text("DELETE FROM form.form_field_options WHERE id = :id"), {"id": saturday.id}
        )


def test_an_answered_question_is_refused_with_the_reason_on_the_screen(client, db_session):
    form, day, _note, saturday, _sunday = _form(db_session)
    headers = _login(client)

    answer = client.post(
        f"/admin/formulieren/{form.id}/velden/{day.id}/verwijderen", headers=headers
    )

    assert answer.status_code == 200, answer.text[:200]
    assert REFUSED_FIELD in answer.text
    db_session.expire_all()
    assert db_session.get(FormField, day.id) is not None
    assert _answer(db_session, saturday.id) is not None


def test_an_unanswered_question_is_removed(client, db_session):
    form, _day, note, _saturday, _sunday = _form(db_session)
    headers = _login(client)

    client.post(f"/admin/formulieren/{form.id}/velden/{note.id}/verwijderen", headers=headers)

    db_session.expire_all()
    assert db_session.get(FormField, note.id) is None


def test_a_definition_laid_over_cannot_drop_a_chosen_option(client, db_session):
    """Laying a definition over a form (the back office's JSON import) runs
    `apply_definition`, which removes every option not in the payload. It relied on
    SET NULL; now it is refused, and nothing is stored."""
    form, day, note, saturday, sunday = _form(db_session)
    payload = {
        "title": "Dagkeuze",
        "status": "open",
        "sections": [],
        "fields": [
            {
                "id": day.id,
                "label": "Welke dag?",
                "field_type": "radio",
                "options": [{"id": sunday.id, "label": "Zondag"}],
            },
            {"id": note.id, "label": "Opmerking", "field_type": "text"},
        ],
    }

    answer = forms_door.update_form(client, form.id, payload)

    assert answer.status_code == 422, answer.text[:300]
    assert "Welke dag?: " + REFUSED_OPTION in answer.json()["detail"]
    db_session.expire_all()
    assert db_session.get(FormFieldOption, saturday.id) is not None
    assert _answer(db_session, saturday.id) is not None


def test_deleting_the_whole_form_still_works(db_session):
    """`delete_form` takes everything: the answers go before the options in the same
    flush, because `FormSubmissionAnswer.option` is mapped, so RESTRICT holds."""
    from app.domains.forms.api import delete_form

    form, _day, _note, saturday, _sunday = _form(db_session)
    delete_form(db_session, form.id)

    assert db_session.get(Form, form.id) is None
    assert _answer(db_session, saturday.id) is None
