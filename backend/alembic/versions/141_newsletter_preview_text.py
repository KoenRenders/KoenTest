"""Preview text for the inbox (#984).

The sentence a mail client shows beside the subject. Without it Gmail shows the
first words of the letter — "Beste," — and the association wastes the one line
that decides whether the letter is opened at all. Optional: left empty, the
letter derives it from its own first real sentence.

Idempotent: the column is only added when it is missing.
"""
from alembic import op
import sqlalchemy as sa

revision = "141_2026_09_20_083000"
down_revision = "140_2026_09_19_190000"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("newsletters", schema="newsletter"):
        return False
    return any(c["name"] == "preview_text"
               for c in inspector.get_columns("newsletters", schema="newsletter"))


def upgrade() -> None:
    if not _has_column():
        op.add_column("newsletters", sa.Column("preview_text", sa.String(200),
                                               nullable=False, server_default=""),
                      schema="newsletter")


def downgrade() -> None:
    if _has_column():
        op.drop_column("newsletters", "preview_text", schema="newsletter")
