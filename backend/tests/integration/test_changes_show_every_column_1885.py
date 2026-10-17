"""Wijzigingen shows every logged column an update changed (#1885, gate 3's reader).

Each kind of row keeps the summary it had (Koen retypes these lines into the
national programme); what that summary does not show is added to an update as
"<label>: old → new", with the word of the attribute register (CR-33). A long
text is not written out: "<label> gewijzigd", while its old and new text stay in
the history table (Koen, 16 October 2026, "10a").

Broken on purpose (16 October 2026, put back): `_with_more` returning the summary
alone → the three tests that look for an added line fail; the long-text branch
taken out of `_more` → the description test fails, the text standing in the line.
"""

from __future__ import annotations

import pytest

from app.domains.activities.api import ActivityHistory
from app.domains.reporting.changes import all_changes_since
from app.kernel.clock import belgian_today
from app.kernel.logged import snapshot
from tests.conftest import seed_activity_with_product

pytestmark = pytest.mark.ui_agnostisch


def _update(db, obj, **changes):
    for name, value in changes.items():
        setattr(obj, name, value)
    db.flush()
    snapshot(db, obj, operation="update", action="test_update", source="admin_manual", actor="t")
    db.flush()


def _summary_of(db, entity: str, entity_id: int) -> str:
    rows = [
        r
        for r in all_changes_since(db, belgian_today())
        if r["entity"] == entity and r["entity_id"] == entity_id and r["operation"] == "update"
    ]
    assert rows, f"no update row of {entity} #{entity_id}"
    return rows[0]["summary"]


def test_a_changed_location_reads_old_and_new(db_session):
    activity, _component, _product = seed_activity_with_product(db_session)
    _update(db_session, activity, location="Zaal A")
    _update(db_session, activity, location="Zaal B")

    summary = _summary_of(db_session, "Activiteit", activity.id)
    assert summary.startswith(activity.name), "the kind's own summary comes first"
    assert "Locatie: Zaal A → Zaal B" in summary


def test_a_changed_description_is_named_not_written_out(db_session):
    activity, _component, _product = seed_activity_with_product(db_session)
    _update(db_session, activity, description="De eerste tekst van de omschrijving.")
    _update(db_session, activity, description="Een heel andere tekst.")

    summary = _summary_of(db_session, "Activiteit", activity.id)
    assert "Omschrijving gewijzigd" in summary
    assert "andere tekst" not in summary, "a long text is not written out (10a)"
    rows = (
        db_session.query(ActivityHistory)
        .filter(ActivityHistory.activity_id == activity.id)
        .order_by(ActivityHistory.id)
        .all()
    )
    assert rows[-1].description == "Een heel andere tekst.", "the full text stays stored"


def test_a_product_made_free_reads_as_yes_and_no(db_session):
    _activity, _component, product = seed_activity_with_product(db_session)
    _update(db_session, product, is_free=False)
    _update(db_session, product, is_free=True, price=0)

    summary = _summary_of(db_session, "Product", product.id)
    assert "Gratis: nee → ja" in summary


def test_an_update_that_changes_nothing_else_keeps_its_summary(db_session):
    activity, _component, _product = seed_activity_with_product(db_session)
    _update(db_session, activity, location="Zaal A")
    _update(db_session, activity, location="Zaal A")

    assert _summary_of(db_session, "Activiteit", activity.id) == activity.name
