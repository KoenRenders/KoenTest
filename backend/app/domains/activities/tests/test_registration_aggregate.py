"""CR-13 phase 1 (#757): `Registration` as an aggregate — the B8 tests of its rules.

Where each rule of a registration lives now (§B4.2), and a test per address:

| rule | address | test |
|---|---|---|
| a name, an e-mail address | `@validates` + `NOT NULL`/`CHECK` | 2, 3 and the edit screen below |
| a mobile number | the entrances (`service.require_phone`): new, or changed | 4 |
| a team name when the component asks for one | `check()`, run on flush | 1b, 5 |

The mobile number has no database constraint (Koen, 29 September 2026); the
entrances still require it.

Proven additively, each run and removed (the CR-12 B8 form):
- the two directions of 1b below are that proof for the listener;
- migration 168 on a table holding a blank e-mail address → it refuses, naming
  the rule and the count, and changes nothing (the test below does it);
- the edit screen with a cleared e-mail address → refused, with the message on
  the screen (the test below).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domains.activities.models import (
    ActivityError,
    ActivitySubRegistration,
    Registration,
)
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.kernel import rules
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_agnostisch

MIGRATION = next(
    (Path(__file__).resolve().parents[4] / "alembic" / "versions").glob("168_*registration*.py")
)


def _registration(activity, component, **overrides):
    values = dict(
        activity_id=activity.id,
        component_id=component.id,
        registration_type="INDIVIDUAL",
        contact_name="An Janssens",
        contact_email="an@example.org",
        phone="0470000000",
        team_name="A-team",
    )
    values.update(overrides)
    return Registration(**values)


@pytest.fixture
def world(db_session):
    activity, component, product = seed_activity_with_product(db_session, is_free=False)
    component.team_name_required = True
    db_session.flush()
    return activity, component


# ── 1b. The listener fires without a call site ───────────────────────────────


def test_a_missing_team_name_is_refused_at_flush_without_calling_anything(db_session, world):
    activity, component = world
    registration = _registration(activity, component, team_name=None)
    db_session.add(registration)
    with pytest.raises(ActivityError, match="ploegnaam"):
        db_session.flush()
    db_session.expunge(registration)


def test_without_the_listener_the_same_flush_goes_through(db_session, world):
    """The other direction: the refusal above comes from the listener."""
    activity, component = world
    rules.uninstall_flush_checks()
    try:
        db_session.add(_registration(activity, component, team_name=None))
        db_session.flush()
    finally:
        rules.install_flush_checks()


# ── 2. Absence is caught at rest ─────────────────────────────────────────────


def test_a_registration_built_without_a_name_is_refused_by_the_database(db_session, world):
    """`@validates` does not fire on a field that is never assigned; NOT NULL does."""
    activity, component = world
    values = dict(
        activity_id=activity.id,
        component_id=component.id,
        registration_type="INDIVIDUAL",
        contact_email="an@example.org",
        team_name="A-team",
    )
    db_session.add(Registration(**values))
    with pytest.raises(IntegrityError, match="contact_name"):
        db_session.flush()


# ── 3. A bulk path cannot store a blank ──────────────────────────────────────


def test_a_bulk_update_to_a_blank_name_is_refused_by_the_constraint(db_session, world):
    activity, component = world
    registration = _registration(activity, component)
    db_session.add(registration)
    db_session.flush()
    with pytest.raises(IntegrityError, match="ck_registrations_contact_name_not_blank"):
        db_session.query(Registration).filter(Registration.id == registration.id).update(
            {"contact_name": "   "}, synchronize_session=False
        )


# ── The validators, on assignment ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("contact_name", "  ", "Vul een naam in."),
        ("contact_name", None, "Vul een naam in."),
        ("contact_email", "", "Vul een geldig e-mailadres in."),
        ("contact_email", "geen-adres", "Vul een geldig e-mailadres in."),
    ],
)
def test_a_validator_refuses_on_assignment(db_session, world, field, value, message):
    """On a loaded row too — the path the admin screen went wrong on (#757)."""
    activity, component = world
    registration = _registration(activity, component)
    db_session.add(registration)
    db_session.flush()
    with pytest.raises(ActivityError, match=message):
        setattr(registration, field, value)


def test_the_validators_keep_the_value_as_given(db_session, world):
    """No stripping: what is stored today stays what is stored (R13)."""
    activity, component = world
    registration = _registration(activity, component, contact_name=" An ")
    assert registration.contact_name == " An "


# ── 4. The mobile number: at the entrances, not at rest ──────────────────────


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _edit_form(**overrides):
    fields = {
        "contact_name": "An Janssens",
        "contact_email": "an@example.org",
        "phone": "0470000000",
        "team_name": "A-team",
        "remarks": "",
    }
    fields.update(overrides)
    return fields


def test_a_registration_without_a_phone_stays_editable(client, db_session, world):
    """No database constraint on the registration phone (Koen, 29 September 2026),
    and a registration stored without one stays editable without adding one — the
    check runs when the number changes. The screen sends every field, the empty
    phone included."""
    activity, component = world
    registration = _registration(activity, component, phone=None)
    db_session.add(registration)
    db_session.flush()

    response = client.post(
        f"/admin/inschrijvingen/{registration.id}/opslaan",
        headers=_login(client),
        data=_edit_form(phone="", remarks="Nieuwe opmerking"),
    )
    assert response.status_code == 200, response.text
    assert 'role="alert"' not in response.text, response.text
    db_session.expire_all()
    stored = db_session.get(Registration, registration.id)
    assert stored.remarks == "Nieuwe opmerking"
    assert stored.phone is None


def test_a_mobile_number_cannot_be_cleared(client, db_session, world):
    """The other direction: an existing number cleared is refused, with the message,
    and nothing is stored."""
    activity, component = world
    registration = _registration(activity, component)
    db_session.add(registration)
    db_session.flush()

    response = client.post(
        f"/admin/inschrijvingen/{registration.id}/opslaan",
        headers=_login(client),
        data=_edit_form(phone="  ", remarks="Nieuwe opmerking"),
    )
    assert response.status_code == 200, response.text
    assert "Vul een mobiel nummer in." in response.text
    db_session.expire_all()
    stored = db_session.get(Registration, registration.id)
    assert stored.phone == "0470000000"
    assert stored.remarks is None


def test_a_new_registration_without_a_phone_is_refused(client, db_session, world):
    """The third direction: every new registration needs a number, on the JSON API
    as on the forms."""
    activity, component = world
    product = component.products[0]
    response = client.post(
        f"/api/v1/activities/{activity.id}/register",
        json={
            "contact_name": "An Janssens",
            "contact_email": "an@example.org",
            "phone": "",
            "team_name": "A-team",
            "component_id": component.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": 1}],
        },
    )
    assert response.status_code == 422, response.text
    assert "Vul een mobiel nummer in." in response.text


# ── The named failure path: the board cannot clear an e-mail address ────────


def test_the_edit_screen_refuses_a_cleared_email_address_and_shows_why(client, db_session, world):
    """Koen, 29 September 2026: the board can change an address, not clear it. The
    refusal is shown in the screen's error banner (200, htmx swaps it) and nothing
    is stored."""
    activity, component = world
    registration = _registration(activity, component)
    db_session.add(registration)
    db_session.flush()

    headers = _login(client)
    refused = client.post(
        f"/admin/inschrijvingen/{registration.id}/opslaan",
        headers=headers,
        data=_edit_form(contact_email="   "),
    )
    assert refused.status_code == 200, refused.text
    assert 'role="alert"' in refused.text
    assert "Vul een geldig e-mailadres in." in refused.text
    db_session.expire_all()
    assert db_session.get(Registration, registration.id).contact_email == "an@example.org"

    changed = client.post(
        f"/admin/inschrijvingen/{registration.id}/opslaan",
        headers=headers,
        data=_edit_form(contact_email="nieuw@example.org"),
    )
    assert changed.status_code == 200, changed.text
    db_session.expire_all()
    assert db_session.get(Registration, registration.id).contact_email == "nieuw@example.org"


# ── 5. The rule reads what is loaded — built without one database round trip ─


def test_check_runs_on_an_object_built_by_hand():
    """No session anywhere: the component is set by hand, never loaded. A `check()`
    that lazy-loaded would fail here instead of querying in production."""
    component = ActivitySubRegistration(id=1, name="Ploegen", team_name_required=True)
    registration = Registration(
        contact_name="An", contact_email="an@example.org", component_id=1, team_name=None
    )
    registration.component = component
    with pytest.raises(ActivityError, match="ploegnaam"):
        registration.check()
    registration.team_name = "A-team"
    registration.check()
    component.team_name_required = False
    registration.team_name = None
    registration.check()


# ── The migration refuses what it cannot constrain ───────────────────────────


def _migration():
    spec = importlib.util.spec_from_file_location("migration_168", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_stops_on_a_blank_email_and_names_it(db_session, world):
    """Proof, additive: a table holding a blank e-mail address. The constraint is
    dropped for the test (inside the test's transaction, rolled back after), a blank
    row written raw, and the migration run → it refuses with the rule and the
    count, and adds nothing."""
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    activity, component = world
    connection = db_session.connection()
    connection.execute(
        text(
            "ALTER TABLE activities.registrations "
            "DROP CONSTRAINT ck_registrations_contact_email_not_blank"
        )
    )
    registration = _registration(activity, component)
    db_session.add(registration)
    db_session.flush()
    connection.execute(
        text("UPDATE activities.registrations SET contact_email = '' WHERE id = :id"),
        {"id": registration.id},
    )

    migration = _migration()
    assert migration.data_check(connection) == ["1 registration(s) without contact_email"]
    with Operations.context(MigrationContext.configure(connection)):
        with pytest.raises(migration.DataCheckFailed, match="without contact_email"):
            migration.upgrade()
    checks = connection.execute(
        text(
            "SELECT count(*) FROM pg_constraint "
            "WHERE conname = 'ck_registrations_contact_email_not_blank'"
        )
    ).scalar()
    assert checks == 0, "a refused migration added the constraint anyway"


def test_the_migration_passes_a_clean_table(db_session, world):
    """The other direction: nothing to refuse, nothing reported."""
    connection = db_session.connection()
    assert _migration().data_check(connection) == []
