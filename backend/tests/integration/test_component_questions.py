"""CR-14 phase 2 (#1333): a component asks the questions of a form — which forms,
and when it may no longer change (§B4.5, §B1.1 F2, F11, F13; B7 tests 6, 9, 14).

- Only a form a registration page can ask is attached: open, not anonymous, one
  section, no maximum, and the tenant's own. Each refusal says its own reason.
- Once attached, closing the form in the builder does not close the component.
- Replacing the form is refused once a registration has answered; detaching is
  allowed and the answers stay.
- A form, or one submission, whose answers a registration holds is not deleted —
  refused with the reason, and both still there.

Broken on purpose to check these tests can go red (run, then restored), with what
failed: the anonymous line in `forms.service.attach_refusal` removed → the
anonymous case of `test_a_form_that_cannot_be_asked_is_refused_with_its_reason`;
`component.form_id is not None and` changed to `False and` in `_check_questions` →
`test_replacing_is_refused_once_answered_detaching_is_not`; the `attached` checks in
`forms.service.delete_form` / `delete_submission` changed to `False and …` → the two
delete tests; `take_answers` asking `component.form_id` instead of
`question_form(db, component)` → the deleted-form test.

The references into `form` are soft (no foreign key across schemas, #396): what a
`RESTRICT` key would have refused, the builder refuses by the `attached` mark, and a
component whose form is deleted asks nothing.
"""

from __future__ import annotations

import pytest

from app.domains.activities import service
from app.domains.activities.api import Registration
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.api import FormulierFout, delete_form, delete_submission
from app.domains.forms.models import Form, FormSubmission
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID, current_tenant_id
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product, seed_question_form


def _attach(db, component, form_id):
    return service.update_component(
        db, component.activity_id, component.id, {"form_id": form_id}, actor="test"
    )


def _answered(db, component, form):
    """A registration on `component` whose answers are a submission of `form`."""
    # `attached`, as `forms.api.submit_attached` marks every registration's answers.
    submission = FormSubmission(form_id=form.id, submitter_name="Ward", attached=True)
    db.add(submission)
    db.flush()
    registration = Registration(
        activity_id=component.activity_id,
        component_id=component.id,
        registration_type="INDIVIDUAL",
        contact_name="Ward",
        contact_email="ward@example.com",
        form_submission_id=submission.id,
    )
    db.add(registration)
    db.commit()
    return registration, submission


@pytest.mark.parametrize(
    "settings, reason",
    [
        ({"status": "closed"}, "staat niet open"),
        ({"is_anonymous": True}, "anoniem formulier"),
        ({"sections": 2}, "meer dan één sectie"),
        ({"max_submissions": 40}, "maximum aantal inzendingen"),
    ],
)
def test_a_form_that_cannot_be_asked_is_refused_with_its_reason(db_session, settings, reason):
    _activity, component, _product = seed_activity_with_product(db_session)
    form = seed_question_form(db_session, **settings)
    with pytest.raises(service.ActiviteitFout, match=reason):
        _attach(db_session, component, form.id)
    db_session.refresh(component)
    assert component.form_id is None


def test_another_tenants_form_is_not_found(db_session):
    _activity, component, _product = seed_activity_with_product(db_session)
    form = seed_question_form(db_session, tenant_id=TENANT_VOORBEELD_ID)
    token = current_tenant_id.set(TENANT_MILLEGEM_ID)
    try:
        with pytest.raises(service.ActiviteitFout, match="bestaat niet"):
            _attach(db_session, component, form.id)
    finally:
        current_tenant_id.reset(token)


def test_an_open_form_is_attached_and_closing_it_later_changes_nothing(db_session):
    _activity, component, _product = seed_activity_with_product(db_session)
    form = seed_question_form(db_session)
    _attach(db_session, component, form.id)
    assert component.form_id == form.id

    form.status = "closed"
    db_session.commit()
    # Saving the component again with the same form: not a new attach, so the
    # form's status is not looked at again (F2).
    _attach(db_session, component, form.id)
    assert component.form_id == form.id
    assert service.registration_refusal(component.activity, component=component) is None


def test_replacing_is_refused_once_answered_detaching_is_not(db_session):
    _activity, component, _product = seed_activity_with_product(db_session)
    sint = seed_question_form(db_session)
    other = seed_question_form(db_session, title="Andere vragen")
    _attach(db_session, component, sint.id)
    _registration, submission = _answered(db_session, component, sint)

    with pytest.raises(service.ActiviteitFout, match="al antwoorden"):
        _attach(db_session, component, other.id)
    db_session.refresh(component)
    assert component.form_id == sint.id

    _attach(db_session, component, None)
    assert component.form_id is None
    assert db_session.get(FormSubmission, submission.id) is not None


def test_a_form_held_by_a_registration_is_not_deleted(db_session):
    _activity, component, _product = seed_activity_with_product(db_session)
    form = seed_question_form(db_session)
    _attach(db_session, component, form.id)
    _answered(db_session, component, form)

    with pytest.raises(FormulierFout, match="antwoorden op inschrijvingen"):
        delete_form(db_session, form.id)
    assert db_session.get(Form, form.id) is not None

    loose = seed_question_form(db_session, title="Los")
    delete_form(db_session, loose.id)
    assert db_session.get(Form, loose.id) is None


def test_a_submission_held_by_a_registration_is_not_deleted(db_session):
    _activity, component, _product = seed_activity_with_product(db_session)
    form = seed_question_form(db_session)
    _attach(db_session, component, form.id)
    _registration, submission = _answered(db_session, component, form)

    with pytest.raises(FormulierFout, match="antwoorden van een inschrijving"):
        delete_submission(db_session, form.id, submission.id)
    assert db_session.get(FormSubmission, submission.id) is not None


def test_a_component_whose_form_was_deleted_asks_nothing(client, db_session):
    """A form attached but never answered may be deleted in the builder; the id
    stays behind (a soft reference) and the component simply asks no questions."""
    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
    form = seed_question_form(db_session)
    _attach(db_session, component, form.id)
    delete_form(db_session, form.id)
    db_session.expire_all()

    html = client.get(f"/activiteiten/{activity.id}/inschrijven/{component.id}").text
    assert 'name="questions"' not in html
    r = client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            "contact_name": "Zonder Vragen",
            "contact_email": "zonder@example.com",
            "phone": "0470000000",
            f"product_{product.id}": "1",
        },
        headers={"HX-Request": "true"},
    )
    assert "Je inschrijving is ontvangen." in r.text
    registration = db_session.query(Registration).filter_by(activity_id=activity.id).one()
    assert registration.answer_token is None and registration.form_submission_id is None


@pytest.mark.ui_serverrendered
def test_the_settings_offer_the_form_and_say_why_a_replace_fails(client, db_session):
    activity, component, _product = seed_activity_with_product(db_session)
    sint = seed_question_form(db_session)
    other = seed_question_form(db_session, title="Andere vragen")
    _attach(db_session, component, sint.id)
    _answered(db_session, component, sint)

    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    html = client.get(f"/admin/activiteiten/{activity.id}").text
    assert f'<option value="{sint.id}" selected>Sint 2026</option>' in html
    assert f'<option value="{other.id}" >Andere vragen</option>' in html

    r = client.post(
        f"/admin/activiteiten/{activity.id}/onderdelen/{component.id}",
        data={"name": component.name, "form_id": str(other.id)},
        headers={"X-CSRF-Token": csrf_token_for(value)},
    )
    assert r.status_code == 200
    assert "al antwoorden op zijn vragen" in r.text
