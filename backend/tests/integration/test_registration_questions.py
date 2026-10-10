"""CR-14 phase 2 (#1333): a registration answers the component's questions — now,
or later by link (§B4.2, §B4.3, §B4.8; B7 tests 2, 4, 5, 8, 12).

- **Three entrances, one rule** (test 2): the public page, the board's page and the
  JSON API each refuse "now" with a required question left empty, name the
  question, and store nothing; each stores "later" with an answer link and no
  submission.
- **One transaction** (test 4): nothing is committed before the payment step, so
  a payment that cannot start takes the registration AND its answers back.
- **The link is right** (test 5): the submission belongs to the component's form,
  and its submitter is the registration's contact.
- **Test 8 is not a `check()` rule any more**: the submission lives across the
  schema line, and `check()` reads only what is loaded, with no ORM relationship
  into `form` (#396). "The answers belong to the component's form" holds by
  construction at its one writer, `take_answers` — asserted by test 5 below.
- **The same parser** (test 12): "Andere…" text on a checkbox reaches the
  submission exactly as the form builder's own public form stores it.

Broken on purpose to check these tests can go red (run, then restored), with what
failed: `savepoint.rollback()` removed from `service.register` → the refusal tests
of the three entrances (a registration stays behind); `registration.answer_token =
new_answer_token()` removed from `take_answers` → the "later" tests; the
`submission.form_id != component.form_id` rule in `Registration.check()` turned
into `False and …` → the detached-object test; a `db.commit()` added after the
flush in `forms.service.submit_attached` → the commit-count test (and the three
tests that post "now", whose session then commits under the page).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.domains.activities.api import Registration
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.models import FormSubmission, FormSubmissionAnswer
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    ask_questions,
    form_guard_fields,
    register_at_the_door,
    seed_activity_with_product,
    seed_question_form,
)


@pytest.fixture
def sint(db_session):
    """A free component that asks the Sint questions."""
    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
    form = seed_question_form(db_session)
    ask_questions(db_session, component, form.id)
    return SimpleNamespace(activity=activity, component=component, product=product, form=form)


def _field(form, label):
    return next(f for f in form.fields if f.label == label)


def _option(field, label):
    return next(o for o in field.options if o.label == label)


def _page_form(s, *, questions: str, **answers) -> dict:
    data = {
        "contact_name": "Ward Vragen",
        "contact_email": "ward@example.com",
        "phone": "0470000000",
        f"product_{s.product.id}": "1",
        "questions": questions,
    }
    data.update(answers)
    return data


def _post_page(client, s, channel: str, data: dict):
    if channel == "public":
        client.cookies.clear()
        return client.post(
            f"/activiteiten/{s.activity.id}/inschrijven/{s.component.id}",
            data=data,
            headers={"HX-Request": "true"},
        )
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return client.post(
        f"/admin/activiteiten/{s.activity.id}/inschrijvingen/nieuw",
        data={"onderdeel": str(s.component.id), **data},
        headers={"HX-Request": "true", "X-CSRF-Token": csrf_token_for(value)},
    )


def _post_api(client, s, answers, **extra):
    client.cookies.clear()
    body = {
        **extra,
        "contact_name": "Ward Vragen",
        "contact_email": "ward@example.com",
        "phone": "0470000000",
        "component_id": s.component.id,
        "items": [{"product_id": s.product.id, "quantity": 1}],
    }
    if answers is not None:
        body["answers"] = answers
    return register_at_the_door(client, s.activity.id, json=body)


def _registrations(db, s):
    db.expire_all()
    return db.query(Registration).filter(Registration.activity_id == s.activity.id).all()


def _submissions(db, s):
    return db.query(FormSubmission).filter(FormSubmission.form_id == s.form.id).count()


# ── Three entrances, one rule (B7 test 2) ─────────────────────────────────────


@pytest.mark.parametrize("channel", ["public", "board"])
def test_a_page_refuses_now_without_a_required_answer(client, db_session, sint, channel):
    slot = _field(sint.form, "Tijdslot")
    data = _page_form(sint, questions="now", **{f"f{slot.id}": str(slot.options[0].id)})
    before = len(_registrations(db_session, sint))

    r = _post_page(client, sint, channel, data)

    # #1589: the refusal is the banner alone, naming the question by its field
    # (`f<id>`); the page is not redrawn, so everything typed stays where it is.
    story = _field(sint.form, "Verhaal")
    assert r.status_code == 422
    assert f'data-error-for="f{story.id}"' in r.text, "the refused question is not named"
    assert "Verhaal" in r.text
    assert "<input" not in r.text, "the answer redraws the form"
    assert len(_registrations(db_session, sint)) == before
    assert _submissions(db_session, sint) == 0


def test_the_api_refuses_now_without_a_required_answer(client, db_session, sint):
    slot = _field(sint.form, "Tijdslot")
    r = _post_api(client, sint, [{"field_id": slot.id, "option_ids": [slot.options[0].id]}])
    assert r.status_code == 422
    assert "Verhaal" in r.json()["detail"]
    assert _registrations(db_session, sint) == []
    assert _submissions(db_session, sint) == 0


@pytest.mark.parametrize("channel", ["public", "board", "api"])
def test_later_stores_the_registration_with_a_link(client, db_session, sint, channel):
    if channel == "api":
        r = _post_api(client, sint, None)
        assert r.status_code == 200, r.text
    else:
        _post_page(client, sint, channel, _page_form(sint, questions="later"))
    [registration] = _registrations(db_session, sint)
    assert registration.form_submission_id is None
    assert registration.answer_token and len(registration.answer_token) >= 40
    assert _submissions(db_session, sint) == 0


# ── The link is right (B7 test 5) ─────────────────────────────────────────────


@pytest.mark.parametrize("channel", ["public", "board"])
def test_now_links_a_submission_of_the_components_form(client, db_session, sint, channel):
    slot, story = _field(sint.form, "Tijdslot"), _field(sint.form, "Verhaal")
    data = _page_form(
        sint,
        questions="now",
        **{f"f{slot.id}": str(slot.options[1].id), f"f{story.id}": "Braaf geweest"},
    )
    _post_page(client, sint, channel, data)

    [registration] = _registrations(db_session, sint)
    submission = db_session.get(FormSubmission, registration.form_submission_id)
    assert submission.form_id == sint.form.id
    assert (submission.submitter_name, submission.submitter_email) == (
        registration.contact_name,
        registration.contact_email,
    )
    assert registration.answer_token is None
    assert registration.remarks is None, "a component with questions keeps no remarks (F3)"


def test_the_page_offers_the_choice_now_by_default(client, sint):
    html = client.get(f"/activiteiten/{sint.activity.id}/inschrijven/{sint.component.id}").text
    assert re.search(r'name="questions" value="now"[^>]* checked', html)
    assert not re.search(r'name="questions" value="later"[^>]* checked', html)
    assert f'name="f{_field(sint.form, "Verhaal").id}"' in html
    assert 'name="remarks"' not in html, "the remarks box shows next to the questions (F3)"


# ── One transaction (B7 test 4) ───────────────────────────────────────────────


def test_nothing_is_committed_before_the_payment_step(client, db_session, monkeypatch):
    """The answers, the registration and the payment record are one transaction:
    nothing is committed until the payment step has run, so a payment that cannot
    start (the 502) takes the answers back with the registration.

    Measured, not assumed: counting rows after the 502 proves nothing here, because
    the route's `db.rollback()` also takes this test's own seed back — the counts
    are zero whatever happened. What can go wrong is an early commit (the forms
    side committing its submission, say), and that is what this counts."""
    activity, component, product = seed_activity_with_product(db_session, price="10.00")
    form = seed_question_form(db_session)
    ask_questions(db_session, component, form.id)
    s = SimpleNamespace(activity=activity, component=component, product=product, form=form)
    slot, story = _field(form, "Tijdslot"), _field(form, "Verhaal")
    answers = [
        {"field_id": slot.id, "option_ids": [slot.options[0].id]},
        {"field_id": story.id, "text": "Braaf"},
    ]

    commits = []
    real_commit = db_session.commit
    monkeypatch.setattr(db_session, "commit", lambda: (commits.append(1), real_commit())[1])
    seen = {}

    def _boom(db, **kwargs):
        seen["commits_before_payment"] = len(commits)
        seen["submissions_pending"] = db.query(FormSubmission).filter_by(form_id=form.id).count()
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.domains.activities.router.create_payment_record", _boom)
    r = _post_api(client, s, answers, payment_method="online")

    assert r.status_code == 502, r.text
    assert seen == {"commits_before_payment": 0, "submissions_pending": 1}, seen


# ── The same parser (B7 test 12) ──────────────────────────────────────────────


def test_other_text_is_stored_as_the_form_builder_stores_it(client, db_session, sint):
    slot, story = _field(sint.form, "Tijdslot"), _field(sint.form, "Verhaal")
    other = _option(slot, "Andere")
    posted = {
        f"f{slot.id}": str(_option(slot, "Voormiddag").id),
        f"f{slot.id}_other": "na school",
        f"f{story.id}": "Braaf",
    }
    _post_page(client, sint, "public", _page_form(sint, questions="now", **posted))
    [registration] = _registrations(db_session, sint)

    client.post(
        f"/formulier/{sint.form.share_token}",
        data={
            "submitter_name": "Ward Vragen",
            "submitter_email": "ward@example.com",
            **posted,
            **form_guard_fields(),
        },
    )
    standalone = (
        db_session.query(FormSubmission)
        .filter(
            FormSubmission.form_id == sint.form.id,
            FormSubmission.id != registration.form_submission_id,
        )
        .one()
    )

    def rows(submission_id):
        return sorted(
            (a.field_id, a.value_option_id, a.value_text)
            for a in db_session.query(FormSubmissionAnswer).filter(
                FormSubmissionAnswer.submission_id == submission_id
            )
        )

    attached = rows(registration.form_submission_id)
    assert attached == rows(standalone.id)
    assert (slot.id, other.id, "na school") in attached
