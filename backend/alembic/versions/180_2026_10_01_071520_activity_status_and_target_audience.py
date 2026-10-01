"""An activity gets a status (draft or published) and a target audience.

#1428, Koen 1 October 2026. With copying (#1397) the board makes next year's
programme in the app instead of a spreadsheet, and that needs a draft that
stays off the public site, and the spreadsheet's "P" column: who an activity is
for.

Every activity that exists is on the public site today, so every one becomes
`published`; the column's server default does that in one statement. The target
audience stays empty: nothing is guessed, the board picks.

No CHECK constraint stands on `activities.activities` (checked: the existing
ones are on components, products and organisers), so none is in the way.
"""

import sqlalchemy as sa
from alembic import op

from app.domains.activities.codes import ACTIVITY_STATUS_CODES, TARGET_AUDIENCE_CODES
from app.kernel.codes import create_code_list

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
revision = "180_2026_10_01_071520"
down_revision = "179_2026_10_01_074523"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    conn = op.get_bind()
    return {c["name"] for c in sa.inspect(conn).get_columns("activities", schema="activities")}


def upgrade() -> None:
    columns = _columns()
    if "status" not in columns:
        op.add_column(
            "activities",
            sa.Column(
                "status", sa.String(20), nullable=False, server_default=sa.text("'published'")
            ),
            schema="activities",
        )
    if "target_audience" not in columns:
        op.add_column(
            "activities",
            sa.Column("target_audience", sa.String(20), nullable=True),
            schema="activities",
        )
    create_code_list(
        op,
        schema="activities",
        name="activity_status",
        codes=ACTIVITY_STATUS_CODES,
        fk_from=("activities.activities.status",),
    )
    create_code_list(
        op,
        schema="activities",
        name="target_audience",
        codes=TARGET_AUDIENCE_CODES,
        fk_from=("activities.activities.target_audience",),
    )


def downgrade() -> None:
    # Schema only, and lossy on purpose: the drafts become indistinguishable from
    # published activities again, and the chosen audiences are gone.
    op.drop_constraint(
        "fk_activities_target_audience_code", "activities", schema="activities", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_activities_status_code", "activities", schema="activities", type_="foreignkey"
    )
    op.drop_table("target_audience_labels", schema="activities")
    op.drop_table("target_audience_codes", schema="activities")
    op.drop_table("activity_status_labels", schema="activities")
    op.drop_table("activity_status_codes", schema="activities")
    op.drop_column("activities", "target_audience", schema="activities")
    op.drop_column("activities", "status", schema="activities")
