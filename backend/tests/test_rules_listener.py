"""CR-13 §B4.2 and §B8 test 1b — an aggregate's check() fires on every flush.

No aggregate carries a check() yet (phase 1 brings `Registration`), so these
tests give an existing model a temporary one and remove it afterwards.
`Activity` is the stand-in: it has a soft-delete column and few required fields.

The heart is the pair: an invalid object is refused at flush **without anyone
calling check()**, and with the listener removed the very same flush goes
through — so the test is known to be looking at the listener and not at
something else that happens to refuse.

Broken on purpose to check these tests can go red (run, then restored), and
additively: one line `uninstall_flush_checks()` added right after the install in
`app/kernel/rules.py` → three tests fail: the listener is not installed, the
invalid activity is not refused, and the valid one's check() never ran.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.domains.activities.api import Activity
from app.kernel import rules

BROKEN = "check() refused: a name reading 'broken'"


def _check(self) -> None:
    if self.name == "broken":
        raise ValueError(BROKEN)


@pytest.fixture
def activity_is_an_aggregate(monkeypatch):
    monkeypatch.setattr(Activity, "check", _check, raising=False)
    rules.aggregate(Activity)
    yield
    rules.unregister_aggregate(Activity)


def test_the_listener_is_installed_on_every_session():
    import app.database  # noqa: F401 — the import that installs it in the application

    assert event.contains(Session, "before_flush", rules._check_on_flush)


def test_an_invalid_aggregate_is_refused_at_flush_without_a_call_site(
    db_session, activity_is_an_aggregate
):
    db_session.add(Activity(name="broken"))
    with pytest.raises(ValueError, match="a name reading 'broken'"):
        db_session.flush()
    db_session.rollback()


def test_a_valid_aggregate_flushes_and_its_check_did_run(db_session, monkeypatch):
    calls: list[str] = []

    def counting_check(self) -> None:
        calls.append(self.name)

    monkeypatch.setattr(Activity, "check", counting_check, raising=False)
    rules.aggregate(Activity)
    try:
        db_session.add(Activity(name="fine"))
        db_session.flush()
    finally:
        rules.unregister_aggregate(Activity)
    assert calls == ["fine"], "the flush went through, but check() never ran"


def test_without_the_listener_the_same_flush_succeeds(db_session, activity_is_an_aggregate):
    """The other direction: proves the refusal above comes from the listener."""
    rules.uninstall_flush_checks()
    try:
        db_session.add(Activity(name="broken"))
        db_session.flush()
    finally:
        rules.install_flush_checks()


def test_a_soft_deleted_aggregate_is_not_checked(db_session, activity_is_an_aggregate):
    """Deleting a legacy row that breaks today's rule must stay possible."""
    from datetime import datetime, timezone

    activity = Activity(name="broken", deleted_at=datetime.now(timezone.utc))
    db_session.add(activity)
    db_session.flush()


def test_an_aggregate_without_check_is_refused():
    class NoRule:
        pass

    with pytest.raises(TypeError, match="has no check"):
        rules.aggregate(NoRule)


def test_every_derived_value_names_an_owner_that_exists():
    import importlib

    values = rules.derived_values()
    assert values, "the derived-value registry is empty — the one-owner gate would be blind"
    missing = []
    for value in values.values():
        module, _, attr = value.today.rpartition(".")
        if not callable(getattr(importlib.import_module(module), attr, None)):
            missing.append(f"{value.name}: {value.today}")
    assert not missing, f"registered owners that do not exist: {missing}"


def test_a_derived_value_cannot_have_two_owners():
    with pytest.raises(ValueError, match="registered twice"):
        rules.derived_value("registration.total", today="x.y", target="x.z", phase=1)
