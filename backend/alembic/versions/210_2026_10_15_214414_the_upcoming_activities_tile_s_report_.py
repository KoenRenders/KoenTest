"""the upcoming activities tile's report says all statuses

#1979: the dashboard's tile "Komende activiteiten" counts every activity whose
last day has not passed — drafts and cancelled ones included — while the public
list shows only what is published and not cancelled. Koen chose to keep the
count and let the name say it (14 October 2026: "b"), in the words "Komende
activiteiten (alle statussen)" (15 October 2026: "a"). The tile's label is code;
the title of the report behind it is a stored row, seeded per tenant by
migration 107, so it changes here.

Only the built-in report: a copy a user made is the user's own (its
`builtin_key` is empty) and keeps its name. Run twice, the second run changes
nothing: it matches on the old name.
"""

from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "210_2026_10_15_214414"
down_revision = "209_2026_10_15_163129"
branch_labels = None
depends_on = None

OLD = "Dashboard — Komende activiteiten"
NEW = "Dashboard — Komende activiteiten (alle statussen)"


def _rename(before: str, after: str) -> None:
    op.execute(
        "UPDATE reporting.saved_reports SET name = '"
        + after
        + "' WHERE builtin_key = 'dashboard_upcoming_activities' AND name = '"
        + before
        + "'"
    )


def upgrade() -> None:
    _rename(OLD, NEW)


def downgrade() -> None:
    # Restores the data too: the built-in report gets its old title back.
    _rename(NEW, OLD)
