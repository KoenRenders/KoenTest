"""#1509 — every tenant has a contact form that works.

- A tenant made with `create_tenant` has its own `berichten` form and its own
  `bericht` definition, and a message through its /berichten makes a submission
  and a Werkbank task — beside raakmillegem's, which keep theirs (the keys are
  per tenant since migration 190).
- A tenant without them shows no "Contacteer ons", and a direct POST gets the
  readable "tijdelijk niet beschikbaar" instead of a 500.
- The startup seed fills in what a tenant lacks; a second start changes nothing.

Proven red, each rule broken on its own on this branch: the forms handler that
does not seed fails the first test; the button following the module alone fails
the two button tests; a contact form that does not ask for the definition fails
the third; a seed without its existence check fails the last. Without migration
190, `create_tenant` fails on the global slug index once the form is seeded —
measured while building (23 tests red).
"""

from __future__ import annotations

import secrets

import pytest

from app.domains.forms.api import CONTACT_FORM_SLUG, Form, FormSubmission
from app.domains.mdm.api import TenantKind, create_tenant
from app.domains.workflow.api import MESSAGE_WORKFLOW, WorkflowTask
from app.domains.workflow.models import WorkflowDefinition
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from seed_contact_forms import seed_contact_forms
from tests.conftest import form_guard_fields

pytestmark = pytest.mark.ui_serverrendered


def _all(db, model):
    return db.query(model).execution_options(include_all_tenants=True)


def _forms(db, tenant_id: int) -> list:
    return _all(db, Form).filter(Form.tenant_id == tenant_id, Form.slug == CONTACT_FORM_SLUG).all()


def _definitions(db, tenant_id: int) -> list:
    return (
        _all(db, WorkflowDefinition)
        .filter(
            WorkflowDefinition.tenant_id == tenant_id,
            WorkflowDefinition.code == MESSAGE_WORKFLOW,
        )
        .all()
    )


def _known_to_the_app(monkeypatch, db) -> None:
    """The middleware reads tenant codes and module sets through its own session,
    which does not see this test's tenant; give it what the test's session sees
    (as `test_screens_follow_modules` sets the module cache)."""
    from app.domains.mdm import tenant_lookup
    from app.domains.mdm.api import enabled_modules

    codes = tenant_lookup.tenant_codes(db)
    monkeypatch.setattr(tenant_lookup, "_cache", codes)
    monkeypatch.setattr(
        tenant_lookup,
        "_modules_cache",
        {tid: enabled_modules(tid, db=db) for tid in codes.values()},
    )


def _bare_tenant(db, code: str):
    """A tenant as the ones created before #1509: no contact form, no definition."""
    tenant = create_tenant(db, name=f"Kaal {code}", code=code, kind=TenantKind.COMPANY)
    for row in (*_forms(db, tenant.id), *_definitions(db, tenant.id)):
        db.delete(row)
    db.commit()
    return tenant


def test_a_new_tenant_has_a_contact_form_that_makes_a_task(
    client, db_session, platform_host, monkeypatch
):
    tenant = create_tenant(db_session, name="Bakkerij", code="bakkerij-1509")
    assert len(_forms(db_session, tenant.id)) == 1
    assert len(_definitions(db_session, tenant.id)) == 1
    assert len(_forms(db_session, TENANT_MILLEGEM_ID)) == 1, "raakmillegem keeps its own"

    _known_to_the_app(monkeypatch, db_session)
    name = f"Afzender {secrets.token_hex(3)}"
    answer = client.post(
        "/bakkerij-1509/berichten",
        headers={"host": platform_host},
        data={**form_guard_fields(), "naam": name, "email": "a@example.com", "bericht": "Brood?"},
    )

    assert answer.status_code == 200, answer.text[:300]
    db_session.expire_all()
    submission = (
        _all(db_session, FormSubmission).filter(FormSubmission.submitter_name == name).one()
    )
    assert submission.tenant_id == tenant.id
    task = (
        _all(db_session, WorkflowTask).filter(WorkflowTask.subject_id == str(submission.id)).one()
    )
    assert task.tenant_id == tenant.id


def test_without_a_contact_form_there_is_no_button_and_no_500(
    client, db_session, platform_host, monkeypatch
):
    _bare_tenant(db_session, "kaal-1509")

    _known_to_the_app(monkeypatch, db_session)
    home = client.get("/kaal-1509/", headers={"host": platform_host}).text
    answer = client.post(
        "/kaal-1509/berichten",
        headers={"host": platform_host},
        data={
            **form_guard_fields(),
            "naam": "Iemand",
            "email": "a@example.com",
            "bericht": "Hallo",
        },
    )

    assert "Contacteer ons" not in home
    assert answer.status_code == 200
    assert "tijdelijk niet beschikbaar" in answer.text


def test_a_form_without_its_definition_is_no_contact_form(
    client, db_session, platform_host, monkeypatch
):
    """The form alone is not enough: without the definition, `start` refuses and
    the message would be rolled back with a 500."""
    tenant = create_tenant(db_session, name="Half", code="half-1509", kind=TenantKind.COMPANY)
    for row in _definitions(db_session, tenant.id):
        db_session.delete(row)
    db_session.commit()

    _known_to_the_app(monkeypatch, db_session)
    home = client.get("/half-1509/", headers={"host": platform_host}).text
    answer = client.post(
        "/half-1509/berichten",
        headers={"host": platform_host},
        data={
            **form_guard_fields(),
            "naam": "Iemand",
            "email": "a@example.com",
            "bericht": "Hallo",
        },
    )

    assert "Contacteer ons" not in home
    assert answer.status_code == 200 and "tijdelijk niet beschikbaar" in answer.text


def test_the_startup_seed_fills_in_and_a_second_start_changes_nothing(db_session):
    tenant = _bare_tenant(db_session, "oud-1509")

    first = seed_contact_forms(db_session)
    assert "oud-1509: contactformulier + werkbankdefinitie" in first
    assert len(_forms(db_session, tenant.id)) == 1
    assert len(_definitions(db_session, tenant.id)) == 1
    counts = (_all(db_session, Form).count(), _all(db_session, WorkflowDefinition).count())

    assert seed_contact_forms(db_session) == [], "a second start adds nothing"
    assert (_all(db_session, Form).count(), _all(db_session, WorkflowDefinition).count()) == counts
