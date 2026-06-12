"""Rename Dutch CMS placeholder codes to English

Replaces {{lidgeld_vol}}, {{lidgeld_half}}, {{halfprijs_start}},
{{halfprijs_einde}}, {{volgend_jaar_vanaf}} with their English equivalents
in all cms_pages content.

Revision ID: 029
Revises: 028
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None

_RENAMES = [
    ("{{lidgeld_vol}}", "{{membership_price_full}}"),
    ("{{lidgeld_half}}", "{{membership_price_half}}"),
    ("{{halfprijs_start}}", "{{half_price_start}}"),
    ("{{halfprijs_einde}}", "{{half_price_end}}"),
    ("{{volgend_jaar_vanaf}}", "{{next_year_from}}"),
]

_RENAMES_REVERSE = [(new, old) for old, new in _RENAMES]


def _apply(conn, replacements):
    for old, new in replacements:
        conn.execute(
            sa.text(
                "UPDATE cms_pages SET content = replace(content, :old, :new), "
                "updated_at = now() WHERE content LIKE :pattern"
            ),
            {"old": old, "new": new, "pattern": f"%{old}%"},
        )


def upgrade():
    conn = op.get_bind()
    _apply(conn, _RENAMES)


def downgrade():
    conn = op.get_bind()
    _apply(conn, _RENAMES_REVERSE)
