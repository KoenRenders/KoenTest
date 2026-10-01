"""organisers without a limit of three (#1429)

An activity can have more than three organisers: the quiz has six (Koen,
1 October 2026). The three belonged to the Design Studio poster, which has room
for three, not to the activity. Migration 133 put the three in the database as
`CHECK (sort_order IN (0, 1, 2))`; this one replaces it with `sort_order >= 0`,
so the database still refuses a nonsense position but no longer a fourth
organiser. The UNIQUE on (activity_id, sort_order) stays: two organisers never
share a place in the order.

Idempotent: each constraint is only dropped or created when the database says
it is (not) there.
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
revision = "179_2026_10_01_074523"
down_revision = "178_2026_10_01_045833"
branch_labels = None
depends_on = None

SCHEMA = "activities"
TABLE = "activity_organisers"
OLD = "ck_activity_organiser_max_three"
NEW = "ck_activity_organiser_sort_order_not_negative"


def _has_check(name: str) -> bool:
    checks = sa.inspect(op.get_bind()).get_check_constraints(TABLE, schema=SCHEMA)
    return any(c["name"] == name for c in checks)


def upgrade() -> None:
    if _has_check(OLD):
        op.drop_constraint(OLD, TABLE, schema=SCHEMA, type_="check")
    if not _has_check(NEW):
        op.create_check_constraint(NEW, TABLE, "sort_order >= 0", schema=SCHEMA)


def downgrade() -> None:
    # Schema only, and only when the data allows it: the old CHECK cannot come
    # back while an activity has an organiser at position 3 or later. Rather
    # than delete organisers to make it fit, the downgrade stops and says so.
    bind = op.get_bind()
    beyond = bind.execute(
        sa.text(f"SELECT count(*) FROM {SCHEMA}.{TABLE} WHERE sort_order > 2")
    ).scalar()
    if beyond:
        raise RuntimeError(
            f"{beyond} organiser(s) at position 3 or later; the limit of three "
            "cannot be restored without removing them. Remove them first."
        )
    if _has_check(NEW):
        op.drop_constraint(NEW, TABLE, schema=SCHEMA, type_="check")
    if not _has_check(OLD):
        op.create_check_constraint(OLD, TABLE, "sort_order IN (0, 1, 2)", schema=SCHEMA)
