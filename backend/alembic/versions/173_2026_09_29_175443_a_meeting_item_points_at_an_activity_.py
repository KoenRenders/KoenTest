"""A meeting item points at one date of an activity (#1335).

A board evaluates the last ride, not the activity: "Fietsen (maandelijks)" has a
ride every month, and a point that only knows the activity cannot say which one
was discussed, nor put the guide of next month's ride next to the guide of the
one after. So an activity point gets the date row it is about.

**Additive**: one nullable column. A point from before this migration keeps
`activity_date_id` NULL and renders the activity as it did; the old app never
reads the column. No backfill: which ride an old point meant is not in the data.

A soft-ref like `activity_id` next to it, not a foreign key: a key across schemas
ties two domains' deploys together (`test_schema_boundaries`).
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
revision = "173_2026_09_29_175443"
down_revision = "172_2026_09_29_111421"
branch_labels = None
depends_on = None


def _columns(conn) -> set[str]:
    rows = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'meetings' AND table_name = 'meeting_items'"
        )
    ).fetchall()
    return {r[0] for r in rows}


def upgrade() -> None:
    if "activity_date_id" in _columns(op.get_bind()):
        return
    op.add_column(
        "meeting_items",
        sa.Column("activity_date_id", sa.Integer(), nullable=True),
        schema="meetings",
    )
    op.create_index(
        "ix_meetings_meeting_items_activity_date_id",
        "meeting_items",
        ["activity_date_id"],
        schema="meetings",
    )


def downgrade() -> None:
    # Schema only: the dates the points carried are gone after this. The points
    # themselves stay, each still naming its activity.
    op.drop_index(
        "ix_meetings_meeting_items_activity_date_id",
        table_name="meeting_items",
        schema="meetings",
    )
    op.drop_column("meeting_items", "activity_date_id", schema="meetings")
