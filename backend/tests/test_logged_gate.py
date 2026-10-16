"""Refuses a column of a logged model that its history table does not carry · hard · since #1885.

Koen, 10 October 2026: is every change to a person, a household or a membership
certain to reach Wijzigingen? It was not: a new column on `Person` needed a
migration on its history table and a line in its snapshot, both by memory, and
five columns had been missed. Koen, 15 October 2026: every model Wijzigingen
reads is logged, every column of it, except an uploaded document's content and
a purely technical moment.

The declaration is `app/kernel/logged.py`, made by each domain in its
`history.py`. This gate reads it:

- **every column** of a declared model is in its history table, or is named as
  not logged with its reason (`not_logged`, the technical moments included);
- **every history table** belongs to a declared model — a history table whose
  model is not declared is a model logged by hand, outside the rule.

The gate counts before it judges: it must find the declarations and the
history tables, or it would pass anything.

Gate 3 — every logged column is shown by Wijzigingen — reads the reader, so it
stands with the reader: `app/domains/reporting/tests/test_the_changes_screen_shows_every_logged_column.py`.

Broken on purpose (16 October 2026, by adding a line, put back): a column
`gate_proof = Column(String(20))` added to `Activity` → the first test failed
naming `Activity.gate_proof`.
"""

from __future__ import annotations


def _history_models() -> list[type]:
    from app.database import Base

    return [
        mapper.class_
        for mapper in Base.registry.mappers
        if mapper.class_.__name__.endswith("History")
        and {"operation", "action", "source", "actor"}
        <= set(mapper.class_.__table__.columns.keys())
    ]


def test_every_column_of_a_logged_model_is_in_its_history_table():
    import app.main  # noqa: F401  every domain's declarations
    from app.kernel.logged import declared, history_column, logged_columns

    entries = declared()
    assert len(entries) >= 12, (
        f"only {len(entries)} declarations — are the history modules imported?"
    )
    missing = []
    for entry in entries:
        carried = set(entry.history.__table__.columns.keys())
        assert entry.key in carried, f"{entry.history.__name__} has no {entry.key}"
        for column in logged_columns(entry):
            if history_column(entry, column) not in carried:
                missing.append(f"{entry.model.__name__}.{column}")
    assert not missing, (
        "a column of a logged model that its history table does not carry — add it to the "
        "history model and a migration, or name it as not logged with its reason in the "
        f"domain's history.py (#1885): {missing}"
    )


def test_every_history_table_belongs_to_a_declared_model():
    import app.main  # noqa: F401
    from app.kernel.logged import declared

    histories = _history_models()
    assert len(histories) >= 12, f"only {len(histories)} history models found"
    covered = {entry.history for entry in declared()}
    outside = sorted(h.__name__ for h in histories if h not in covered)
    assert not outside, (
        "a history table whose model is not declared — declare it in its domain's "
        f"history.py, so the gates hold it (#1885): {outside}"
    )
