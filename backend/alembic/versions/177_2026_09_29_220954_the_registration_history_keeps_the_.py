"""The registration history keeps the answers (CR-14 phase 3, #1334, §B4.7).

An organiser may correct a registration's answers on its detail. Such a quiet
correction of what a member said needs a trace, as the correction of contact
details has had since #624: one row per change, the previous row the old value.
`registration_history` had no place for the answers, so it gets one nullable text
column, "label: value" per line, filled on the rows of an action that concerns the
answers. #1334 said "no migration"; the column was decided on 30 September 2026
(master CLI) over writing the answers into `remarks`, which would make a column
mean something else than its name.

**Additive** (#1255): one nullable column, no data step, not read by the old app.
The table was checked for CHECK constraints on this column: none, it is new.
"""

import sqlalchemy as sa
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
revision = "177_2026_09_29_220954"
down_revision = "176_2026_09_29_210332"
branch_labels = None
depends_on = None


#: #1255: this migration declares what it is. One new nullable column.
ADDITIVE = True


def _columns(conn) -> set[str]:
    return {
        c["name"] for c in sa.inspect(conn).get_columns("registration_history", schema="activities")
    }


def upgrade() -> None:
    if "answers" not in _columns(op.get_bind()):
        op.add_column(
            "registration_history",
            sa.Column("answers", sa.Text(), nullable=True),
            schema="activities",
        )


def downgrade() -> None:
    # Schema only, and it loses data: the answers recorded on history rows go with
    # the column; the rows themselves stay.
    if "answers" in _columns(op.get_bind()):
        op.drop_column("registration_history", "answers", schema="activities")
