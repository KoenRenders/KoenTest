"""The forms tests' way into the forms domain, in process (CR-13 phase 4b, #1251).

The JSON routes under `/api/v1/forms` had no caller but their own tests and are
gone. What those tests proved was almost never the route: it was a rule of the
domain — a definition that jumps backwards is refused, a required question is
asked for, an anonymous form stores nobody — reached through the only door that
took a whole definition or a whole submission as one value. The rules live in
`forms.service` and in the one submit function both ways in shared; the screens
reach them field by field.

So the tests keep their definitions and their submissions as they were, and hand
them to the same functions the screens call:

* a definition → `service.create_form`, then the three steps of
  `service.import_definition` (validate, settings, sections and questions), the
  path of the back office's JSON import — without its rollback on a refusal: a
  request's rollback ends the request, a test's would undo the test's own set-up
  (`_lay_over`);
* a submission → `forms.api.submit_public_form`, the function the public screen
  posts to;
* a changed submission → `forms.api.update_public_submission`, the edit link's.

An `Answer` carries what the tests read from a response — `status_code` and
`json()` — so a refusal is still asserted by its code and its message. The codes
are the ones the functions raise (`HTTPException`), 422 for a definition the
schema or the service refuses, 404 for a form that does not exist.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException
from pydantic import ValidationError

from app.domains.forms import api as forms_api
from app.domains.forms import service
from app.domains.forms.schemas import FormCreate, FormUpdate, SubmissionIn
from app.kernel.form_guard import Proof
from app.kernel.jobs import run_due_jobs


class Answer:
    """What a test reads from a response: the status code and the body."""

    def __init__(self, status_code: int, body: Any = None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        return self._body

    @property
    def text(self) -> str:
        return repr(self._body)

    def __repr__(self) -> str:
        return f"<Answer {self.status_code} {self._body!r}>"


def _answer(call: Callable[[], Any]) -> Answer:
    try:
        return Answer(200, call())
    except HTTPException as exc:
        return Answer(exc.status_code, {"detail": exc.detail})
    except ValidationError as exc:
        return Answer(422, {"detail": exc.errors(include_context=False, include_url=False)})
    except service.FormulierFout as exc:
        return Answer(422, {"detail": str(exc)})
    except LookupError as exc:
        return Answer(404, {"detail": str(exc)})


def _db(client):
    """The session behind a test client: the one its requests run on.

    The `client` fixture overrides `get_db` with the test's own session, so a
    test that set its form up through the client keeps doing so in one
    transaction. A session handed in directly is used as it is.
    """
    from app.database import get_db

    app = getattr(client, "app", None)
    if app is None:
        return client
    return next(app.dependency_overrides[get_db]())


def _plain(model) -> Any:
    return model.model_dump(mode="json") if hasattr(model, "model_dump") else model


def _lay_over(db, form, data) -> None:
    """What `service.import_definition` does, step for step, and committed.

    A refusal (`FormulierFout`) comes before `apply_definition` changes a row;
    what `update_settings` set on the object is dropped with `expire`, so the
    form is read from the database again — nothing of a refused definition
    is stored, which is what the tests of a refusal assert.
    """
    try:
        service.validate_definition(data)
        service.update_settings(form, data)
        service.apply_definition(form, data)
    except Exception:
        db.expire(form)
        raise
    db.commit()
    db.refresh(form)


def create_form(client, payload: dict) -> Answer:
    """A new form from a whole definition; the body is the definition as stored."""

    db = _db(client)

    def call():
        data = FormCreate.model_validate(payload)
        service.validate_definition(data)
        form = service.create_form(
            db, title=data.title, share_token=forms_api.unique_share_token(db), status=data.status
        )
        _lay_over(db, form, data)
        return read_form(db, form.id)

    return _answer(call)


def read_form(client, form_id: int) -> dict:
    """The definition as stored, with its ids — what the builder works on."""
    db = _db(client)
    db.expire_all()
    return _json(forms_api.form_definition(db, service.get_form(db, form_id)))


def update_form(client, form_id: int, payload: dict) -> Answer:
    """A whole definition laid over an existing form, as the JSON import does."""

    db = _db(client)

    def call():
        form = service.get_form(db, form_id)
        _lay_over(db, form, FormUpdate.model_validate(payload))
        return read_form(db, form_id)

    return _answer(call)


def submit(client, share_token: str, body: dict) -> Answer:
    """One public submission, through the function the public screen posts to.

    The guard's two fields travel in the body, as they did (`form_guard_fields`).
    The confirmation mail is a background task of the request; it is run here,
    after the submission, as the server does after the response.
    """

    db = _db(client)

    def call():
        data = SubmissionIn.model_validate(body)
        proof = Proof(honeypot=data.website, token=data.form_ts, client_ip="test")
        result = forms_api.submit_public_form(db, share_token, data, proof=proof)
        # The confirmation is a queued job since CR-13 phase 4d; the runner picks
        # it up after the commit — here, where the request's background task ran.
        run_due_jobs(db)
        return _plain(result)

    return _answer(call)


def update_submission(client, edit_token: str, body: dict) -> Answer:
    """A person's own submission changed through the edit link."""

    db = _db(client)

    def call():
        data = SubmissionIn.model_validate(body)
        return _plain(forms_api.update_public_submission(db, edit_token, data))

    return _answer(call)


def _json(value: Any) -> Any:
    """As a JSON response gave it: decimals and dates as a client read them."""
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(value)


def results(client, form_id: int) -> dict:
    """The results of a form as the back office's results tab computes them."""
    from app.domains.forms.results import compute_results

    db = _db(client)
    return _json(compute_results(db, service.get_form(db, form_id)))


def submissions(client, form_id: int) -> dict:
    """The submissions of a form, one row each, as the submissions tab lists them."""
    from app.domains.forms.export import build_submissions_view

    db = _db(client)
    return _json(build_submissions_view(db, service.get_form(db, form_id)))


def delete_submission(client, form_id: int, submission_id: int) -> None:
    """One submission removed, through the service the submissions tab calls."""
    service.delete_submission(_db(client), form_id, submission_id)


def export_ods(client, form_id: int):
    """The submissions as a spreadsheet: the response the export screen returns."""
    return forms_api.export_submissions_ods(_db(client), form_id)


def read_submission(client, edit_token: str) -> Answer:
    """A person's own submission as the edit link finds it: the form, who sent it
    and one entry per answered question."""
    db = _db(client)
    db.expire_all()
    submission = service.get_submission_by_edit_token(db, edit_token)
    if submission is None:
        return Answer(404, {"detail": "Inzending niet gevonden"})
    by_field: dict[int, dict] = {}
    for row in submission.answers:
        entry = by_field.setdefault(
            row.field_id,
            {
                "field_id": row.field_id,
                "text": None,
                "number": None,
                "option_ids": [],
                "rating": None,
                "other_text": None,
            },
        )
        if row.value_option_id is not None:
            entry["option_ids"].append(row.value_option_id)
            # The text on an option's row is the free "Andere…" text (#337).
            if row.value_text is not None:
                entry["other_text"] = row.value_text
        elif row.value_text is not None:
            entry["text"] = row.value_text
        if row.value_number is not None:
            entry["number"] = row.value_number
        if row.value_rating is not None:
            entry["rating"] = row.value_rating
    return Answer(
        200,
        _json(
            {
                "form": read_form(db, submission.form_id),
                "submitter_name": submission.submitter_name,
                "submitter_email": submission.submitter_email,
                "answers": list(by_field.values()),
            }
        ),
    )
