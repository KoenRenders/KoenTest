"""A deleted submission closes its open task on the werkbank (#1377).

Found on 30 September 2026 while clearing spam on PROD: a message through
"Contacteer ons" starts a "behartigen" task (`SubmissionCreated`), but deleting
the message published nothing, so the task stayed open and pointed at a
submission that no longer existed. `forms` now reports `SubmissionDeleted`, and
`workflow` closes the submission's open task with a reason.

The tests go through the admin route that deletes a submission, so they also
prove the wiring: a subscriber that is never called leaves them red.

Proven red against master `5d92eb2b` (this file on an export of it): the first
and the last test failed, the task was still open after the delete. The other two
passed there as well, as they must: they guard what the change must not touch.
"""

from __future__ import annotations

import secrets

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.models import Form, FormSubmission
from app.domains.workflow import api
from app.domains.workflow.models import RunStatus, TaskStatus, WorkflowInstance, WorkflowTask
from tests.conftest import SEEDED_ADMIN_EMAIL, form_guard_fields

pytestmark = pytest.mark.ui_serverrendered

REASON = "Automatisch gesloten: inzending verwijderd."


def _message(client, db) -> tuple[FormSubmission, WorkflowTask]:
    """A message through the public form, with the task it starts."""
    name = f"Afzender {secrets.token_hex(3)}"
    answer = client.post(
        "/berichten",
        data={**form_guard_fields(), "naam": name, "email": "a@example.com", "bericht": "Spam"},
    )
    assert answer.status_code == 200, answer.text[:200]
    submission = db.query(FormSubmission).filter(FormSubmission.submitter_name == name).one()
    task = db.query(WorkflowTask).filter(WorkflowTask.subject_id == str(submission.id)).one()
    assert task.status is TaskStatus.OPEN
    return submission, task


def _delete(client, submission: FormSubmission) -> None:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    answer = client.post(
        f"/admin/formulieren/{submission.form_id}/inzendingen/{submission.id}/verwijderen",
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )
    assert answer.status_code == 200, answer.text[:200]


def test_deleting_a_message_closes_its_open_task(client, db_session):
    submission, task = _message(client, db_session)
    submission_id, task_id = submission.id, task.id

    _delete(client, submission)

    db_session.expire_all()
    assert db_session.get(FormSubmission, submission_id) is None, "the message is deleted"
    task = db_session.get(WorkflowTask, task_id)
    assert task.status is TaskStatus.DONE, "the task of a deleted message is closed"
    assert task.decision == REASON and task.done_by == "systeem"
    instance = db_session.get(WorkflowInstance, task.instance_id)
    assert instance.status is RunStatus.DONE, "and its workflow ends, with no next step"
    later = db_session.query(WorkflowTask).filter(WorkflowTask.instance_id == instance.id)
    assert later.count() == 1, "no task for a next step was made"


def test_a_task_already_closed_keeps_its_decision(client, db_session):
    submission, task = _message(client, db_session)
    api.close_task(db_session, task.id, done_by="koen@example.com", decision="Beantwoord")
    db_session.commit()
    task_id = task.id

    _delete(client, submission)

    db_session.expire_all()
    task = db_session.get(WorkflowTask, task_id)
    assert task.status is TaskStatus.DONE
    assert (task.decision, task.done_by) == ("Beantwoord", "koen@example.com")


def test_a_submission_of_another_form_touches_no_task(client, db_session):
    _, task = _message(client, db_session)
    tag = secrets.token_hex(3)
    other = Form(title="Opruimdag", slug=f"opruimdag-{tag}", status="open", share_token=tag)
    db_session.add(other)
    db_session.flush()
    submission = FormSubmission(form_id=other.id, submitter_name="Iemand")
    db_session.add(submission)
    db_session.commit()
    open_before = db_session.query(WorkflowTask).filter(WorkflowTask.status == TaskStatus.OPEN)
    count = open_before.count()
    assert count >= 1, "there is an open task that could be touched"

    _delete(client, submission)

    db_session.expire_all()
    assert db_session.get(WorkflowTask, task.id).status is TaskStatus.OPEN
    assert open_before.count() == count, "no open task was closed"


def test_deleting_a_whole_form_closes_the_tasks_of_its_submissions(client, db_session):
    """`delete_form` takes the submissions with it (cascade). Each is a deleted
    submission like any other, so its open task closes too."""
    tag = secrets.token_hex(3)
    form = Form(title="Opruimdag", slug=f"opruimdag-{tag}", status="open", share_token=tag)
    db_session.add(form)
    db_session.flush()
    submission = FormSubmission(form_id=form.id, submitter_name="Iemand")
    db_session.add(submission)
    db_session.flush()
    task = api.create_task(
        db_session,
        kind="bericht.behartigen",
        title=f"Behartigen {tag}",
        subject_type="form_submission",
        subject_id=str(submission.id),
        required_role="ADMIN",
    )
    db_session.commit()
    task_id = task.id
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)

    answer = client.post(
        f"/admin/formulieren/{form.id}/verwijderen",
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )

    assert answer.status_code == 204, answer.text[:200]
    db_session.expire_all()
    task = db_session.get(WorkflowTask, task_id)
    assert task.status is TaskStatus.DONE and task.decision == REASON
