"""CR-13 phase 4c, P1 (#1251): the answers of a registration go through a port — what
is written and what is refused stays.

Until P1 `activities` called two commands of `forms` directly
(`forms.api.submit_attached` when a registration answers the component's
questions, `forms.api.update_attached` when the board corrects them). They are
ports now (`kernel/ports.py`, `docs/architecture.md` §3.2.1 step 2):
`SubmitAttached` and `UpdateAttached`, handled in `forms/handlers.py`.

No behaviour changes, so the proof is **the same answer and the same rows on the
same input**: every case below — the door's answer, then the rows it left — was
recorded on the code BEFORE the ports and the code with the ports must give it
again, character for character (`tests/_snapshot.py`). Accepted and refused, for
both ports: a refusal must come through the port as it came from the function.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domains.activities.api import (
    Activity,
    ActivityProduct,
    ActivitySubRegistration,
    Registration,
    RegistrationHistory,
    RegistrationItem,
)
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.models import (
    Form,
    FormField,
    FormFieldOption,
    FormSection,
    FormSubmission,
    FormSubmissionAnswer,
)
from tests._snapshot import compare, fixed_ids, normalise
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    ask_questions,
    register_at_the_door,
    seed_activity_with_product,
    seed_question_form,
)

SNAPSHOTS = Path(__file__).parent / "snapshots" / "answer_ports_1251"
BEFORE = "the answers went through a port (CR-13 phase 4c, P1)"
MODELS = (Activity, ActivitySubRegistration, ActivityProduct, Registration, RegistrationItem)
MODELS += (RegistrationHistory, Form, FormSection, FormField, FormFieldOption)
MODELS += (FormSubmission, FormSubmissionAnswer)


@pytest.fixture
def sint(db_session):
    """A free component that asks the Sint questions: "Tijdslot" (checkbox,
    required, with "Andere…"), "Verhaal" (required) and "Opmerkingen"."""
    with fixed_ids(db_session, MODELS):
        activity, component, product = seed_activity_with_product(
            db_session, price="0", is_free=True
        )
        form = seed_question_form(db_session)
        ask_questions(db_session, component, form.id)
        db_session.commit()
        fields = {f.label: f for f in form.fields}
        yield SimpleNamespace(
            activity=activity,
            component=component,
            product=product,
            form=form,
            slot=fields["Tijdslot"],
            story=fields["Verhaal"],
            remarks=fields["Opmerkingen"],
        )


def _register(client, s, answers):
    client.cookies.clear()
    body = {
        "contact_name": "Ward Poort",
        "contact_email": "ward-1251@example.com",
        "phone": "0470000000",
        "component_id": s.component.id,
        "items": [{"product_id": s.product.id, "quantity": 1}],
        "answers": answers,
    }
    return register_at_the_door(client, s.activity.id, json=body)


def _correct(client, registration_id: int, data: dict):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return client.post(
        f"/admin/inschrijvingen/{registration_id}/antwoorden",
        data=data,
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )


def _rows(db, s) -> str:
    """What stands in the database for this activity's registrations: each
    registration with its submission, every answer row, every history row."""
    db.expire_all()
    lines = []
    for registration in (
        db.query(Registration).filter_by(activity_id=s.activity.id).order_by(Registration.id)
    ):
        lines.append(
            f"registration {registration.id}: submission={registration.form_submission_id} "
            f"answer_link={'yes' if registration.answer_token else 'no'}"
        )
        for row in (
            db.query(RegistrationHistory)
            .filter_by(registration_id=registration.id)
            .order_by(RegistrationHistory.id)
        ):
            if row.action == "answers_edited":
                lines.append(f"  history {row.action} by {row.actor}: {row.answers!r}")
    for submission in (
        db.query(FormSubmission).filter_by(form_id=s.form.id).order_by(FormSubmission.id)
    ):
        lines.append(
            f"submission {submission.id}: form={submission.form_id} attached={submission.attached} "
            f"by {submission.submitter_name} <{submission.submitter_email}>"
        )
        for answer in (
            db.query(FormSubmissionAnswer)
            .filter_by(submission_id=submission.id)
            .order_by(FormSubmissionAnswer.field_id, FormSubmissionAnswer.id)
        ):
            lines.append(
                f"  answer field={answer.field_id} text={answer.value_text!r} "
                f"number={answer.value_number!r} option={answer.value_option_id} "
                f"rating={answer.value_rating!r}"
            )
    return "\n".join(lines) or "(no rows)"


def _record(name: str, answer: str, db, s) -> None:
    today = date.today()
    moving = {today.isoformat(): "<TODAY>", str(today.year): "<YEAR>"}
    got = normalise(f"{answer}\n--- rows ---\n{_rows(db, s)}", {}, moving)
    compare(SNAPSHOTS, name, got, BEFORE)


def _json_answer(response) -> str:
    body = response.json()
    if isinstance(body, dict):
        body = {k: v for k, v in sorted(body.items()) if k not in {"registered_at", "created_at"}}
    return f"{response.status_code}\n{body}"


def _good(s) -> list[dict]:
    return [
        {"field_id": s.slot.id, "option_ids": [s.slot.options[0].id]},
        {"field_id": s.story.id, "text": "Braaf geweest"},
    ]


# ── SubmitAttached: a registration answers the component's questions ─────────


def test_a_registration_with_answers_stores_what_it_stored(client, db_session, sint):
    response = _register(
        client,
        sint,
        [
            {
                "field_id": sint.slot.id,
                "option_ids": [sint.slot.options[1].id, sint.slot.options[2].id],
                "other_text": "Na vieren",
            },
            {"field_id": sint.story.id, "text": "Braaf geweest"},
            {"field_id": sint.remarks.id, "text": "Geen"},
        ],
    )
    assert response.status_code == 200, response.text
    _record("submit_accepted", _json_answer(response), db_session, sint)


@pytest.mark.parametrize(
    "name, answers",
    [
        # A required question left empty: refused, the question named.
        ("submit_refused_required", "ONLY_SLOT"),
        # An option that is not the question's.
        ("submit_refused_foreign_option", "FOREIGN_OPTION"),
        # An answer to a question the component does not ask.
        ("submit_refused_unknown_field", "UNKNOWN_FIELD"),
    ],
)
def test_a_refused_answer_is_refused_as_it_was(client, db_session, sint, name, answers):
    cases = {
        "ONLY_SLOT": [{"field_id": sint.slot.id, "option_ids": [sint.slot.options[0].id]}],
        "FOREIGN_OPTION": [
            {"field_id": sint.slot.id, "option_ids": [999_999]},
            {"field_id": sint.story.id, "text": "Braaf geweest"},
        ],
        "UNKNOWN_FIELD": [*_good(sint), {"field_id": 999_998, "text": "Nergens"}],
    }
    response = _register(client, sint, cases[answers])
    assert response.status_code >= 400, response.text
    _record(name, _json_answer(response), db_session, sint)


# ── UpdateAttached: the board corrects the answers ───────────────────────────


@pytest.fixture
def answered(client, db_session, sint):
    assert _register(client, sint, _good(sint)).status_code == 200
    return db_session.query(Registration).filter_by(activity_id=sint.activity.id).one()


def test_a_correction_stores_what_it_stored(client, db_session, sint, answered):
    response = _correct(
        client,
        answered.id,
        {f"f{sint.slot.id}": str(sint.slot.options[1].id), f"f{sint.story.id}": "Heel braaf"},
    )
    assert response.status_code == 200, response.text[:300]
    _record("update_accepted", f"{response.status_code}\n{response.text}", db_session, sint)


def test_a_refused_correction_is_refused_as_it_was(client, db_session, sint, answered):
    response = _correct(
        client,
        answered.id,
        {f"f{sint.slot.id}": str(sint.slot.options[1].id), f"f{sint.story.id}": ""},
    )
    assert "Verhaal" in response.text
    _record("update_refused", f"{response.status_code}\n{response.text}", db_session, sint)
