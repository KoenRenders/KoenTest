"""CR-14 phase 2 (#1333): answering later, by link (§B4.8, §B5; B7 test 3).

- "Later" sends ONE confirmation mail, and it carries the answer link; the
  thank-you page repeats it.
- The link opens the questions with the first name and the activity — not the
  address or the phone.
- Valid answers are stored once: the submission is linked and the link is spent.
- A spent link and a link that never existed answer the same 404, and a second
  post stores nothing (§B5: nothing revealed). CR-14 B7 test 3 asked for "al
  ingevuld" on a second visit; that cannot hold beside §B5 and the CHECK that
  clears the token, so the 404 page says it: answered already means all is well.
- A refusal names the question and keeps the answers.
- The registration limiter covers the page: its budget is the registration
  routes' own, ten a minute.

Broken on purpose to check these tests can go red (run, then restored), with what
failed: `registration.answer_token = None` removed from `answer_questions` → the
link-once test (the second post stores a second submission — the CHECK refuses it
first, as an error, not the 404); the `answer_url=` argument dropped from the mail
handler → the mail test; `dependencies=[Depends(registration_limiter)]` removed
from the GET → the limiter test.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domains.activities import service
from app.domains.activities.api import Registration
from app.domains.forms.models import FormSubmission
from app.kernel.jobs import KernelJob
from tests.conftest import seed_activity_with_product, seed_question_form

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def later(client, db_session):
    """A registration on a component with questions that chose "later"."""
    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
    form = seed_question_form(db_session)
    service.update_component(db_session, activity.id, component.id, {"form_id": form.id})
    r = client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            "contact_name": "Lore Later",
            "contact_email": "lore@example.com",
            "phone": "0470000000",
            f"product_{product.id}": "1",
            "questions": "later",
        },
        headers={"HX-Request": "true"},
    )
    db_session.expire_all()
    registration = (
        db_session.query(Registration).filter(Registration.activity_id == activity.id).one()
    )
    return SimpleNamespace(
        activity=activity,
        component=component,
        form=form,
        registration=registration,
        token=registration.answer_token,
        thank_you=r.text,
    )


def _answers(form, **overrides) -> dict:
    slot = next(f for f in form.fields if f.label == "Tijdslot")
    story = next(f for f in form.fields if f.label == "Verhaal")
    data = {f"f{slot.id}": str(slot.options[0].id), f"f{story.id}": "Heel braaf"}
    data.update(overrides)
    return data


def test_later_sends_one_mail_with_the_link_and_the_page_repeats_it(db_session, later):
    path = f"/inschrijving/{later.token}/vragen"
    assert path in later.thank_you

    mails = [
        j.payload
        for j in db_session.query(KernelJob).all()
        if j.payload.get("email_type") == "activity_confirmation"
    ]
    assert len(mails) == 1, mails
    assert path in mails[0]["body_html"]
    assert "Nog even de vragen" in mails[0]["body_html"]


def test_the_link_shows_the_questions_and_no_more_than_the_mail(client, later):
    html = client.get(f"/inschrijving/{later.token}/vragen").text
    assert "Inschrijving van Lore voor " in html
    assert later.activity.name in html
    for field in later.form.fields:
        assert f'name="f{field.id}"' in html
    assert "lore@example.com" not in html and "0470000000" not in html


def test_the_answers_are_stored_once_and_the_link_is_spent(client, db_session, later):
    url = f"/inschrijving/{later.token}/vragen"
    r = client.post(url, data=_answers(later.form))
    assert r.status_code == 200
    assert "Je antwoorden zijn bewaard" in r.text and "Heel braaf" in r.text

    db_session.expire_all()
    registration = db_session.get(Registration, later.registration.id)
    assert registration.answer_token is None
    submission = db_session.get(FormSubmission, registration.form_submission_id)
    assert submission.form_id == later.form.id

    again = client.post(url, data=_answers(later.form, **{"x": "y"}))
    assert again.status_code == 404
    assert "al beantwoord" in again.text
    assert client.get(url).status_code == 404
    assert db_session.query(FormSubmission).filter_by(form_id=later.form.id).count() == 1


def test_an_unknown_link_is_the_same_404(client, later):
    r = client.get("/inschrijving/niet-bestaand-token/vragen")
    assert r.status_code == 404
    assert "niet (meer) geldig" in r.text
    assert later.activity.name not in r.text


def test_a_refusal_names_the_question_and_keeps_the_answers(client, db_session, later):
    story = next(f for f in later.form.fields if f.label == "Verhaal")
    slot = next(f for f in later.form.fields if f.label == "Tijdslot")
    r = client.post(
        f"/inschrijving/{later.token}/vragen",
        data={f"f{slot.id}": str(slot.options[1].id), f"f{story.id}": ""},
    )
    # #1589: the refusal is the banner alone, for the form page's message line,
    # naming the question by its field; the page is not redrawn, so the answers
    # given stay where they are.
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#formulier-melding"
    assert f'data-error-for="f{story.id}"' in r.text and "Verhaal" in r.text
    assert "<input" not in r.text
    db_session.expire_all()
    assert db_session.get(Registration, later.registration.id).answer_token == later.token


def test_the_limiter_covers_the_page(client, later):
    # The limiter's budget is shared with the registration routes: the fixture's
    # own registration took one of the ten.
    codes = [client.get("/inschrijving/geen-token/vragen").status_code for _ in range(10)]
    assert codes[:9] == [404] * 9, codes
    assert codes[9] == 429, codes
