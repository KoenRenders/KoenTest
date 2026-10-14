"""Two delete buttons of the form builder say why they refuse (#1858).

A form that holds the answers of a registration is not deleted, and neither is
a submission that is those answers (CR-14 F11): both rules are right. Both doors
answer the kit's refusal into a message line by the button that was pressed
(`says_why_in`), read here as the screen gets it (`tests/_refusal.py`), with the
line found once on the page the board is looking at, and nothing deleted.

Broken on purpose (14 October 2026, each put back): the decorator `says_why_in`
taken off `formulier_verwijderen`, and off `inzending_verwijderen` → its test
fails on the answer, which is no refusal banner.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.models import Form, FormSubmission
from tests import forms_door
from tests._refusal import heading, message_line, said
from tests.conftest import SEEDED_ADMIN_EMAIL

FORM_RULE = (
    "Dit formulier heeft antwoorden op inschrijvingen. Die antwoorden horen bij "
    "de inschrijvingen, dus het formulier blijft zolang zij er zijn."
)
SUBMISSION_RULE = (
    "Deze inzending zijn de antwoorden van een inschrijving. Pas ze aan op "
    "de inschrijving; verwijderen kan hier niet."
)


@pytest.fixture
def held(client, db_session):
    """A form with one submission that is the answers of a registration."""
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    headers = {"X-CSRF-Token": csrf_token_for(session)}
    form_id = forms_door.create_form(client, {"title": "Inschrijving", "sections": []}).json()["id"]
    submission = FormSubmission(form_id=form_id, attached=True)
    db_session.add(submission)
    db_session.flush()
    return {
        "headers": headers,
        "base": f"/admin/formulieren/{form_id}",
        "form_id": form_id,
        "submission_id": submission.id,
    }


def _refused_in(client, page: str, answer, rule: str, line: str) -> None:
    assert answer.status_code == 422
    assert heading(answer) == "Opslaan is niet gelukt."
    assert said(answer) == [rule]
    assert message_line(answer) == line
    shown = client.get(page, headers={"HX-Request": "true"}).text
    assert shown.count(f'id="{line.lstrip("#")}"') == 1, f"the page has no line {line}"


def test_a_form_that_holds_a_registrations_answers_says_why_by_its_button(client, db_session, held):
    answer = client.post(f"{held['base']}/verwijderen", headers=held["headers"])

    _refused_in(client, held["base"], answer, FORM_RULE, "#fb-formulier-melding")
    db_session.expire_all()
    assert db_session.get(Form, held["form_id"]) is not None


def test_a_submission_that_is_a_registrations_answers_says_why_in_its_row(client, db_session, held):
    submission = held["submission_id"]
    answer = client.post(
        f"{held['base']}/inzendingen/{submission}/verwijderen", headers=held["headers"]
    )

    _refused_in(
        client,
        f"{held['base']}/inzendingen",
        answer,
        SUBMISSION_RULE,
        f"#fb-inzending-{submission}-melding",
    )
    db_session.expire_all()
    assert db_session.get(FormSubmission, submission) is not None
