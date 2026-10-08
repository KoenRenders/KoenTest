"""CR-13 phase 4c, C7-1 (#1251): copying a component's question form goes through a
port — what is written stays.

Copying an activity with its components copies each component's question form
too, and the copied component gets the new form's id (#1397). Until C7-1
`activities` called `forms.api.copy_form` for it, a command of another domain
with an answer; it is the port `CopyForm` now (`kernel/contracts/forms.py`,
handled in `forms/handlers.py`).

No behaviour changes, so the proof is **the same rows on the same input**: the
copied components and every row of the copied forms — the form, its sections,
its questions, their options — were recorded on the code BEFORE the port, and
the code with the port must write them again, character for character
(`tests/_snapshot.py`).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.domains.activities.api import (
    Activity,
    ActivityDate,
    ActivityProduct,
    ActivitySubRegistration,
    copy_activity,
)
from app.domains.forms.models import Form, FormField, FormFieldOption, FormSection
from tests._snapshot import compare, fixed_ids, normalise
from tests.conftest import ask_questions, seed_activity_with_product, seed_question_form

SNAPSHOTS = Path(__file__).parent / "snapshots" / "copy_form_port_1251"
BEFORE = "the copy of a question form went through a port (CR-13 phase 4c, C7-1)"
MODELS = (Activity, ActivityDate, ActivitySubRegistration, ActivityProduct)
MODELS += (Form, FormSection, FormField, FormFieldOption)


def _component(db, activity, name: str, form) -> ActivitySubRegistration:
    component = ActivitySubRegistration(
        activity_id=activity.id, name=name, registration_type_code="INDIVIDUAL", is_free=True
    )
    db.add(component)
    db.flush()
    if form is not None:
        ask_questions(db, component, form.id)
    return component


def _rows(db, activity) -> str:
    """The components of this activity and every row of the forms they ask."""
    db.expire_all()
    lines = []
    components = (
        db.query(ActivitySubRegistration)
        .filter_by(activity_id=activity.id)
        .order_by(ActivitySubRegistration.id)
    )
    for component in components:
        lines.append(f"component {component.id} {component.name!r}: form={component.form_id}")
        if component.form_id is None:
            continue
        form = db.get(Form, component.form_id)
        lines.append(
            f"  form {form.id}: title={form.title!r} slug={form.slug!r} status={form.status} "
            f"token={'yes' if form.share_token else 'no'}"
        )
        for section in db.query(FormSection).filter_by(form_id=form.id).order_by(FormSection.id):
            lines.append(f"  section {section.id}: {section.title!r} at {section.position}")
        for field in db.query(FormField).filter_by(form_id=form.id).order_by(FormField.id):
            lines.append(
                f"  field {field.id}: {field.label!r} {field.field_type} "
                f"required={field.required} at {field.position} in section {field.section_id}"
            )
            for option in (
                db.query(FormFieldOption).filter_by(field_id=field.id).order_by(FormFieldOption.id)
            ):
                lines.append(
                    f"    option {option.id}: {option.label!r} at {option.position} "
                    f"other={bool(option.is_other)}"
                )
    return "\n".join(lines)


def test_a_copied_activity_copies_its_question_forms_as_it_did(db_session):
    """Three components: one asks a form with the year in its title, one a form
    without a year, one asks nothing — the three ways the copy treats a form."""
    with fixed_ids(db_session, MODELS):
        forms_before = db_session.query(Form).count()
        source, first, _product = seed_activity_with_product(db_session, price="0", is_free=True)
        day = db_session.query(ActivityDate).filter_by(activity_id=source.id).one()
        day.start_date = date(2026, 12, 5)
        ask_questions(db_session, first, seed_question_form(db_session, title="Sint 2026").id)
        _component(
            db_session, source, "Zonder jaar", seed_question_form(db_session, title="Wensen")
        )
        _component(db_session, source, "Vraagt niets", None)
        db_session.commit()

        copy = copy_activity(
            db_session, source.id, first_date=date(2027, 12, 4), with_components=True, actor="proef"
        )
        db_session.commit()

        assert copy is not None
        recorded = (
            f"--- source ---\n{_rows(db_session, source)}\n--- copy ---\n{_rows(db_session, copy)}"
        )
        compare(SNAPSHOTS, "copied_forms", normalise(recorded, {}, {}), BEFORE)
        added = db_session.query(Form).count() - forms_before
        assert added == 4, f"{added} forms added: the two source forms and their two copies"


def test_a_form_that_does_not_exist_is_refused_through_the_port(db_session):
    """The refusal `forms.api.copy_form` gave — a `LookupError` — comes through
    the port untouched, and no form is made."""
    import pytest

    import app.main  # noqa: F401 — registers the handlers
    from app.kernel.contracts.forms import CopyForm
    from app.kernel.ports import call

    forms_before = db_session.query(Form).count()
    with pytest.raises(LookupError):
        call(CopyForm(form_id=999_999, old_year=2026, new_year=2027), db_session)
    assert db_session.query(Form).count() == forms_before
