"""An activity remembers the activity it was copied from (#1397).

Koen, 1 October 2026: a copied Design Studio design points at last year's
photos, but the photo choice showed only the media of the copy itself — an
empty list. With this link the photo choice can offer the photos and design
images of the activities before it, as references; nothing is copied.

Nullable, and no foreign key: activities are soft-deleted, and a link to a
deleted predecessor is history, not an error. Additive: the previous release
never reads or writes the column.
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
revision = "178_2026_10_01_045833"
down_revision = "177_2026_09_29_220954"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    columns = {c["name"] for c in sa.inspect(conn).get_columns("activities", schema="activities")}
    if "copied_from_id" not in columns:
        op.add_column(
            "activities",
            sa.Column("copied_from_id", sa.Integer(), nullable=True),
            schema="activities",
        )


def downgrade() -> None:
    # Drops the link only; the copies themselves stay, without knowing their
    # predecessor — their photo choice then shows their own media again.
    op.drop_column("activities", "copied_from_id", schema="activities")
