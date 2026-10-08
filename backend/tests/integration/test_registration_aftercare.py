"""CR-14 phase 3 (#1334): the aftercare — the answers in the mail (R6, AC8) and
the answer link sent (again) by the board (§B4.8).

- A registration that answered "now" gets one confirmation mail that lists its
  answers, label and value, after the products and the payment information.
- One that chose "later" gets the link and no answers; a component without
  questions gets neither — the mail it always got.
- "Link opnieuw sturen" sends the open link again, with a reminder subject;
  "link sturen" gives a registration from before the form its first link; an
  answered registration has none to send. Each send leaves one history row.
- An organiser corrects an answer on the detail: the same fields and the same
  rules — an empty required answer is refused there too, the question marked,
  nothing changed; a correction replaces the answers and leaves one history row
  with each changed answer as "label: old → new"; a save that changes nothing
  leaves none.

Broken on purpose to check these tests can go red (run, then restored), with what
failed: `answers=answers,` dropped from the mail handler → the "now" test; the
`record_registration_history(...)` call removed from `send_answer_link` → the two
send tests; the toast back to `ui.toast_oob()` without the route's words (the
#1367 quirk) → the send-again test; `answer_link_action` answering "opnieuw" for an answered registration
→ the answered test; `update_attached` changed to skip `build_answers` (rows
from the posted answers unvalidated) → the refusal test, and the correction
test with it (the checkbox answer is lost unparsed); the `if changes:` guard
removed from `edit_answers` → the correction test (a second row for an unchanged
save).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domains.activities import service
from app.kernel.jobs import KernelJob
from tests.conftest import register_at_the_door, seed_activity_with_product, seed_question_form

pytestmark = pytest.mark.ui_agnostisch


@pytest.fixture
def sint(db_session):
    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
    form = seed_question_form(db_session)
    service.update_component(db_session, activity.id, component.id, {"form_id": form.id})
    return SimpleNamespace(activity=activity, component=component, product=product, form=form)


def _register(client, s, answers):
    body = {
        "contact_name": "Ward Mail",
        "contact_email": "ward@example.com",
        "phone": "0470000000",
        "component_id": s.component.id,
        "items": [{"product_id": s.product.id, "quantity": 1}],
    }
    if answers is not None:
        body["answers"] = answers
    r = register_at_the_door(client, s.activity.id, json=body)
    assert r.status_code == 200, r.text


def _mails(db):
    return [
        j.payload
        for j in db.query(KernelJob).all()
        if j.payload.get("email_type") == "activity_confirmation"
    ]


def test_a_registration_that_answered_gets_its_answers_in_the_mail(client, db_session, sint):
    slot = next(f for f in sint.form.fields if f.label == "Tijdslot")
    story = next(f for f in sint.form.fields if f.label == "Verhaal")
    _register(
        client,
        sint,
        [
            {"field_id": slot.id, "option_ids": [o.id for o in slot.options if not o.is_other]},
            {"field_id": story.id, "text": "Zingt <altijd>"},
        ],
    )
    [mail] = _mails(db_session)
    body = mail["body_html"]
    assert "Jouw antwoorden" in body
    assert "<strong>Tijdslot:</strong> Voormiddag, Namiddag" in body
    assert "<strong>Verhaal:</strong> Zingt &lt;altijd&gt;" in body, "an answer is not escaped"
    assert "<strong>Opmerkingen:</strong> —" in body
    assert body.index("Producten") < body.index("Jouw antwoorden")
    assert "/vragen" not in body


def test_later_gets_the_link_and_no_answers(client, db_session, sint):
    _register(client, sint, None)
    [mail] = _mails(db_session)
    assert "/vragen" in mail["body_html"]
    assert "Jouw antwoorden" not in mail["body_html"]


def test_a_component_without_questions_gets_neither(client, db_session):
    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
    s = SimpleNamespace(activity=activity, component=component, product=product)
    _register(client, s, None)
    [mail] = _mails(db_session)
    assert "Jouw antwoorden" not in mail["body_html"] and "/vragen" not in mail["body_html"]


# ── The answer link, sent (again) by the board (§B4.8) ────────────────────────


def _as_board(client):
    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _reminders(db):
    return [
        j.payload
        for j in db.query(KernelJob).all()
        if j.payload.get("email_type") == "activity_confirmation"
        and j.payload["subject"].startswith("Herinnering")
    ]


def _history(db, registration_id):
    from app.domains.activities.api import RegistrationHistory

    return [
        h.action for h in db.query(RegistrationHistory).filter_by(registration_id=registration_id)
    ]


@pytest.mark.ui_serverrendered
def test_the_board_sends_an_open_link_again(client, db_session, sint):
    from app.domains.activities.api import Registration

    _register(client, sint, None)
    registration = db_session.query(Registration).filter_by(activity_id=sint.activity.id).one()
    token = registration.answer_token
    csrf = _as_board(client)

    detail = client.get(f"/admin/inschrijvingen/{registration.id}").text
    assert "Link opnieuw sturen" in detail
    r = client.post(
        f"/admin/inschrijvingen/{registration.id}/antwoordlink", headers={"X-CSRF-Token": csrf}
    )
    # #1367: the toast says what happened, not the fixed "Opgeslagen ✓".
    assert r.status_code == 200 and "De link naar de vragen is verstuurd." in r.text
    assert "Opgeslagen ✓" not in r.text

    db_session.expire_all()
    assert db_session.get(Registration, registration.id).answer_token == token
    [reminder] = _reminders(db_session)
    assert reminder["subject"] == f"Herinnering: de vragen voor {sint.activity.name}"
    assert f"/inschrijving/{token}/vragen" in reminder["body_html"]
    assert _history(db_session, registration.id) == ["answer_link_sent"]


@pytest.mark.ui_serverrendered
def test_a_registration_from_before_the_form_gets_a_new_link(client, db_session):
    """The form was attached after it registered: no answers, no link — "link
    sturen" makes the token and sends it; nothing else is filled in."""
    from app.domains.activities.api import Registration

    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
    s = SimpleNamespace(activity=activity, component=component, product=product)
    _register(client, s, None)
    form = seed_question_form(db_session)
    service.update_component(db_session, activity.id, component.id, {"form_id": form.id})
    registration = db_session.query(Registration).filter_by(activity_id=activity.id).one()
    assert registration.answer_token is None
    csrf = _as_board(client)

    assert (
        "Link naar de vragen sturen" in client.get(f"/admin/inschrijvingen/{registration.id}").text
    )
    client.post(
        f"/admin/inschrijvingen/{registration.id}/antwoordlink", headers={"X-CSRF-Token": csrf}
    )
    db_session.expire_all()
    registration = db_session.get(Registration, registration.id)
    assert registration.answer_token and registration.form_submission_id is None
    assert len(_reminders(db_session)) == 1
    assert _history(db_session, registration.id) == ["answer_link_sent"]


@pytest.mark.ui_serverrendered
def test_an_answered_registration_has_no_link_to_send(client, db_session, sint):
    from app.domains.activities.api import Registration

    slot = next(f for f in sint.form.fields if f.label == "Tijdslot")
    story = next(f for f in sint.form.fields if f.label == "Verhaal")
    _register(
        client,
        sint,
        [
            {"field_id": slot.id, "option_ids": [slot.options[0].id]},
            {"field_id": story.id, "text": "Braaf"},
        ],
    )
    registration = db_session.query(Registration).filter_by(activity_id=sint.activity.id).one()
    csrf = _as_board(client)
    detail = client.get(f"/admin/inschrijvingen/{registration.id}").text
    assert "Link opnieuw sturen" not in detail and "Link naar de vragen sturen" not in detail
    r = client.post(
        f"/admin/inschrijvingen/{registration.id}/antwoordlink", headers={"X-CSRF-Token": csrf}
    )
    assert "geen vragen meer te beantwoorden" in r.text
    assert _reminders(db_session) == [] and _history(db_session, registration.id) == []


# ── Correcting an answer (R7, AC7, B7 test 10) ────────────────────────────────


@pytest.fixture
def answered(client, db_session, sint):
    from app.domains.activities.api import Registration

    slot = next(f for f in sint.form.fields if f.label == "Tijdslot")
    story = next(f for f in sint.form.fields if f.label == "Verhaal")
    _register(
        client,
        sint,
        [
            {"field_id": slot.id, "option_ids": [slot.options[0].id]},
            {"field_id": story.id, "text": "Braaf"},
        ],
    )
    registration = db_session.query(Registration).filter_by(activity_id=sint.activity.id).one()
    return SimpleNamespace(s=sint, registration=registration, slot=slot, story=story)


def _save_answers(client, a, data):
    csrf = _as_board(client)
    return client.post(
        f"/admin/inschrijvingen/{a.registration.id}/antwoorden",
        data=data,
        headers={"X-CSRF-Token": csrf},
    )


def _answer_rows(db, a):
    from app.domains.forms.api import submission_views

    db.expire_all()
    sid = a.registration.form_submission_id
    return dict(submission_views(db, [sid])[sid])


@pytest.mark.ui_serverrendered
def test_the_detail_offers_the_answers_to_correct(client, answered):
    _as_board(client)
    html = client.get(f"/admin/inschrijvingen/{answered.registration.id}").text
    assert f'hx-post="/admin/inschrijvingen/{answered.registration.id}/antwoorden"' in html
    assert f'name="f{answered.story.id}"' in html and ">Braaf</textarea>" in html


@pytest.mark.ui_serverrendered
def test_an_empty_required_answer_is_refused_on_edit(client, db_session, answered):
    r = _save_answers(
        client,
        answered,
        {f"f{answered.slot.id}": str(answered.slot.options[1].id), f"f{answered.story.id}": ""},
    )
    assert "Verhaal" in r.text and "ring-red-600" in r.text
    assert _answer_rows(db_session, answered)["Verhaal"] == "Braaf"
    assert _answer_rows(db_session, answered)["Tijdslot"] == "Voormiddag"
    assert _history(db_session, answered.registration.id) == []


@pytest.mark.ui_serverrendered
def test_a_correction_replaces_the_answers_and_records_old_and_new(client, db_session, answered):
    from app.domains.activities.api import RegistrationHistory

    data = {
        f"f{answered.slot.id}": str(answered.slot.options[1].id),
        f"f{answered.story.id}": "Heel braaf",
    }
    r = _save_answers(client, answered, data)
    assert r.status_code == 200
    rows = _answer_rows(db_session, answered)
    assert rows["Tijdslot"] == "Namiddag" and rows["Verhaal"] == "Heel braaf"

    [row] = db_session.query(RegistrationHistory).filter_by(
        registration_id=answered.registration.id
    )
    assert row.action == "answers_edited" and row.actor
    assert row.answers.splitlines() == [
        "Tijdslot: Voormiddag → Namiddag",
        "Verhaal: Braaf → Heel braaf",
    ]
    export = client.get(
        f"/admin/activiteiten/{answered.s.activity.id}/onderdelen/{answered.s.component.id}/export"
    )
    from tests.integration.test_registration_answers_reads import _sheet

    header, *rest = _sheet(export.content)
    row = next(r for r in rest if r[0] == "Ward Mail")
    assert row[header.index("Verhaal")] == "Heel braaf"

    _save_answers(client, answered, data)  # the same again: no second row
    assert _history(db_session, answered.registration.id) == ["answers_edited"]
