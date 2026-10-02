"""design gets an optional poster title

#1461. The poster wants less than the website: the activity "Stappen en
klappen" carries "maandelijks" in its name for the agenda, while the poster
should say only "Stappen en klappen". So a design may name its own poster
title; empty means the activity's name, as before.

This existed once as `title_override` (migration 133) and round 3 dropped it in
migration 140. Koen, 2 October 2026, found it useful after all. It comes back
as a new column with a new name, `poster_title`, and 133 and 140 stay as
merged. The name differs on purpose: 140's downgrade re-adds `title_override`,
and two columns for one fact after a round trip would be worse than none.

`String(255)`, the same as the activity's name: whatever fits as a name fits
as a title. The poster layout has its own limit (a title that overflows is a
planner violation, and the version is refused), so the column does not repeat
it.
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
revision = "185_2026_10_02_082804"
down_revision = "184_2026_10_02_045500"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns WHERE table_schema = 'designstudio' "
                "AND table_name = 'designs' AND column_name = 'poster_title'"
            )
        )
        .first()
    )


def upgrade() -> None:
    if not _has_column():
        op.add_column(
            "designs",
            sa.Column("poster_title", sa.String(255), nullable=True),
            schema="designstudio",
        )


def downgrade() -> None:
    # Schema only: a poster title typed after the upgrade is lost, and the
    # poster falls back to the activity's name.
    if _has_column():
        op.drop_column("designs", "poster_title", schema="designstudio")
