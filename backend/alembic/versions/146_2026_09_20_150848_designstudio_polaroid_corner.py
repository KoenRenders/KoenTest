"""designstudio: polaroid corner

Koen, 20 September 2026: the polaroid always sat bottom right, so on a photo
whose subject is in that corner it covered exactly what mattered. The corner
becomes a choice of the person making the poster — and the picture grows a
fifth, now that it can be put where there is room.

Idempotent: the column is added only when it is missing.
"""
import sqlalchemy as sa
from alembic import op

revision = '146_2026_09_20_150848'
down_revision = '145_2026_09_20_074133'
branch_labels = None
depends_on = None

CORNERS = "('top_left', 'top_right', 'bottom_left', 'bottom_right')"


def _has_column(table: str, column: str) -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'designstudio' AND table_name = :t AND column_name = :c"),
        {"t": table, "c": column}).scalar())


def upgrade() -> None:
    if not _has_column("designs", "inset_corner"):
        op.add_column("designs", sa.Column("inset_corner", sa.String(12), nullable=False,
                                           server_default="bottom_right"), schema="designstudio")
        op.create_check_constraint("ck_design_inset_corner", "designs",
                                   f"inset_corner IN {CORNERS}", schema="designstudio")


def downgrade() -> None:
    # Schema only: a chosen corner is lost, every polaroid returns to bottom right.
    if _has_column("designs", "inset_corner"):
        op.drop_constraint("ck_design_inset_corner", "designs", schema="designstudio")
        op.drop_column("designs", "inset_corner", schema="designstudio")
