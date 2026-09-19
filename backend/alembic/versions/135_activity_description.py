"""A public description on an activity (#1016).

Two or three sentences the board writes once: they show on the activity page
and go into the newsletter block of CR-05 (#984). NOT `activities.notes` —
that column exists but is shown and filled nowhere, so it carries no meaning
to inherit.

Idempotent: the column is only added when it is missing.
"""
from alembic import op
import sqlalchemy as sa

revision = "135_2026_09_19_104500"
down_revision = "134_2026_09_18_145500"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    bind = op.get_bind()
    return bool(sa.inspect(bind).has_table("activities", schema="activities") and any(
        c["name"] == "description"
        for c in sa.inspect(bind).get_columns("activities", schema="activities")))


def upgrade() -> None:
    if not _has_column():
        op.add_column("activities", sa.Column("description", sa.Text(), nullable=True),
                      schema="activities")


def downgrade() -> None:
    if _has_column():
        op.drop_column("activities", "description", schema="activities")
