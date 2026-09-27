"""#1136 — a question moves to another section and keeps its id.

The detour was to delete the question and make it again in the other section.
On a form with submissions that cut every stored answer loose from its
question, because the answers refer to the field's id. Now the edit form of a
question has a **Sectie** list, and saving it moves the row itself.

The four tests the issue asks for, through the real route:

1. the question keeps its id, and the stored answer still points at it;
2. it lands at the bottom of the new section, on a position nobody else has;
3. a move that would make one of its jumps go backwards is refused, and the
   builder's error banner names the option and both sections;
4. a move that touches no jump simply works.

Broken on purpose to check that these tests can go red: the jump check in
`_check_move` removed → test 3 falls over (the move goes through and the jump
now points backwards); the position line removed (the question keeps its old
position) → test 2 falls over on the tie; the move check placed after
`veld.label = label` in `update_field` → test 3 falls over on the label, which
the refused edit had already put on the row.
"""
import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.models import (
    Form,
    FormField,
    FormFieldOption,
    FormSection,
    FormSubmission,
    FormSubmissionAnswer,
)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client) -> str:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


@pytest.fixture
def form(db_session):
    """Three sections; the first holds two questions, the second one."""
    f = Form(title="Verhuizen", share_token="verhuis-token", status="open")
    db_session.add(f)
    db_session.flush()
    sections = []
    for position, title in enumerate(("Eerste", "Tweede", "Derde")):
        section = FormSection(form_id=f.id, title=title, position=position)
        db_session.add(section)
        sections.append(section)
    db_session.flush()
    fields = {}
    for name, section, position, kind in (
            ("keuze", sections[0], 0, "radio"), ("tekst", sections[0], 1, "text"),
            ("daar", sections[1], 0, "text")):
        field = FormField(form_id=f.id, section_id=section.id, field_type=kind,
                          label=f"Vraag {name}", position=position)
        db_session.add(field)
        fields[name] = field
    db_session.flush()
    return f, sections, fields


def _move(client, csrf, form, field, section, **extra):
    data = {"label": field.label, "section_id": str(section.id), **extra}
    return client.post(f"/admin/formulieren/{form.id}/velden/{field.id}", data=data,
                       headers={"X-CSRF-Token": csrf})


def test_a_moved_question_keeps_its_id_and_its_answers(client, db_session, form):
    f, sections, fields = form
    submission = FormSubmission(form_id=f.id, submitter_name="Proef")
    db_session.add(submission)
    db_session.flush()
    answer = FormSubmissionAnswer(submission_id=submission.id,
                                  field_id=fields["tekst"].id, value_text="bewaard")
    db_session.add(answer)
    db_session.flush()
    csrf = _login(client)

    resp = _move(client, csrf, f, fields["tekst"], sections[2])

    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    moved = db_session.get(FormField, fields["tekst"].id)
    assert moved is not None and moved.section_id == sections[2].id
    assert db_session.get(FormSubmissionAnswer, answer.id).field_id == moved.id


def test_it_lands_at_the_bottom_of_the_new_section(client, db_session, form):
    f, sections, fields = form
    csrf = _login(client)

    _move(client, csrf, f, fields["keuze"], sections[1])

    db_session.expire_all()
    in_second = sorted((x for x in db_session.query(FormField).filter_by(
        section_id=sections[1].id)), key=lambda x: x.position)
    assert [x.id for x in in_second] == [fields["daar"].id, fields["keuze"].id]
    assert len({x.position for x in in_second}) == len(in_second), "no tie"
    # …and the section it left keeps a gap-free order.
    left = db_session.query(FormField).filter_by(section_id=sections[0].id).all()
    assert [x.position for x in left] == [0]


def test_a_move_that_breaks_a_jump_is_refused_by_name(client, db_session, form):
    f, sections, fields = form
    db_session.add(FormFieldOption(field_id=fields["keuze"].id, label="Naar twee",
                                   position=0, skip_to_section_id=sections[1].id))
    db_session.flush()
    csrf = _login(client)

    resp = _move(client, csrf, f, fields["keuze"], sections[2], label="Nieuw label")

    # The message is on the screen, in the builder's error banner — not only in
    # a response body the generic error toast never shows (measured at 390 px).
    banner = re.search(r'role="alert"[^>]*>(.*?)</div>', resp.text, re.S)
    assert resp.status_code == 200 and banner, resp.text[:2000]
    assert all(w in banner.group(1) for w in ("Naar twee", "Tweede", "Derde")), banner.group(1)
    # Nothing of the refused edit is applied — not the move, and not the label
    # that came along in the same save, which the screen would otherwise show.
    assert "Nieuw label" not in resp.text
    veld = db_session.get(FormField, fields["keuze"].id)
    assert (veld.section_id, veld.label) == (sections[0].id, "Vraag keuze")


def test_a_move_that_touches_no_jump_works(client, db_session, form):
    f, sections, fields = form
    db_session.add(FormFieldOption(field_id=fields["keuze"].id, label="Naar drie",
                                   position=0, skip_to_section_id=sections[2].id))
    db_session.flush()
    csrf = _login(client)

    resp = _move(client, csrf, f, fields["keuze"], sections[1])

    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    assert db_session.get(FormField, fields["keuze"].id).section_id == sections[1].id
