"""Refuses a logged column that Wijzigingen does not show · hard · since #1885 (gate 3).

A column can be logged and never read: the history row carries it and the
reader compares other fields. Every logged column (`app/kernel/logged.py`) is
shown by Wijzigingen (`reporting/changes.py`): by its kind's own summary, under
its register label (CR-33) in the lines an update adds, or named in `SHOWN` as
not shown, with its reason. Gates 1 and 2 stand in `tests/test_logged_gate.py`.

Broken on purpose (16 October 2026, by adding a line, put back): a column
`gate_proof = Column(String(20))` added to `Activity` AND to `ActivityHistory`
(gate 1 green) → this gate failed naming `Activity.gate_proof`, a logged column
without a word to show it by.
"""

from __future__ import annotations


def test_every_logged_column_is_shown_by_the_changes_screen():
    """Gate 3: a logged column no row of Wijzigingen shows is logged and never
    read. Shown by the kind's own summary, under its register label, or named as
    not shown with its reason."""
    import app.main  # noqa: F401
    from app.domains.reporting.changes import NOT_SHOWN_ANYWHERE, SHOWN, label_of
    from app.kernel.logged import declared, logged_columns

    entries = declared()
    assert len(entries) >= 12, f"only {len(entries)} declarations"
    unread = sorted(e.model.__name__ for e in entries if e.model.__name__ not in SHOWN)
    assert not unread, f"a logged model that Wijzigingen does not read (#1885): {unread}"
    unlabelled = []
    checked = 0
    for entry in entries:
        rules = SHOWN[entry.model.__name__]
        for column in logged_columns(entry):
            if column in rules["shown"] or column in rules["not_shown"]:
                continue
            if column in NOT_SHOWN_ANYWHERE:
                continue
            checked += 1
            attr = label_of(entry.model, column)
            if attr is None or attr.label is None:
                unlabelled.append(f"{entry.model.__name__}.{column}")
    assert checked >= 20, f"only {checked} columns read by the generic lines"
    assert not unlabelled, (
        "a logged column Wijzigingen would show without a word for it — give it a "
        "label in its domain's attributes.py, or name it in `SHOWN` "
        f"(reporting/changes.py) with the reason it is not shown (#1885): {unlabelled}"
    )
