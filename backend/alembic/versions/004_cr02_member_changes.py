"""CR-02: member changes — mobile on persons, board_member on members, updated codes

Revision ID: 004
Revises: 003
Create Date: 2026-06-05 00:00:00.000000
"""
from datetime import datetime
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

_gender_codes_tbl = sa.table(
    "gender_codes",
    sa.column("code", sa.String),
    sa.column("language", sa.String),
    sa.column("value", sa.String),
    sa.column("description", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)

_role_codes_tbl = sa.table(
    "role_codes",
    sa.column("code", sa.String),
    sa.column("language", sa.String),
    sa.column("value", sa.String),
    sa.column("description", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)


def upgrade() -> None:
    # --- Schema changes ---
    op.add_column("persons", sa.Column("mobile", sa.String(30), nullable=True))
    op.add_column("members", sa.Column("board_member_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_members_board_member_id",
        "members", "persons",
        ["board_member_id"], ["id"],
    )

    now = datetime.utcnow()

    # --- Gender codes: rename "O" (Onzijdig) -> Anders X, add Onbekend U ---
    # Update existing "O" code to "X" for "Anders/X"
    op.execute(
        sa.text("UPDATE gender_codes SET code = 'X', value = 'X', description = 'X' WHERE code = 'O'")
    )
    # Add English translations for existing codes
    op.bulk_insert(
        _gender_codes_tbl,
        [
            {"code": "M", "language": "en", "value": "Male", "description": "Male gender", "created_at": now, "updated_at": now},
            {"code": "F", "language": "en", "value": "Female", "description": "Female gender", "created_at": now, "updated_at": now},
            {"code": "X", "language": "en", "value": "X", "description": "X", "created_at": now, "updated_at": now},
            # Unknown
            {"code": "U", "language": "nl", "value": "Onbekend", "description": "Onbekend geslacht", "created_at": now, "updated_at": now},
            {"code": "U", "language": "en", "value": "Unknown", "description": "Unknown gender", "created_at": now, "updated_at": now},
        ],
    )

    # --- Role codes: add member-person relationship types ---
    op.bulk_insert(
        _role_codes_tbl,
        [
            {"code": "HOOFDLID", "language": "nl", "value": "Hoofdlid", "description": "Hoofdlid van het gezin", "created_at": now, "updated_at": now},
            {"code": "HOOFDLID", "language": "en", "value": "Primary member", "description": "Primary member of the household", "created_at": now, "updated_at": now},
            {"code": "PARTNER", "language": "nl", "value": "Partner", "description": "Partner van het hoofdlid", "created_at": now, "updated_at": now},
            {"code": "PARTNER", "language": "en", "value": "Partner", "description": "Partner of the primary member", "created_at": now, "updated_at": now},
            {"code": "KIND", "language": "nl", "value": "(Meerderjarig) kind", "description": "Meerderjarig kind van het gezin", "created_at": now, "updated_at": now},
            {"code": "KIND", "language": "en", "value": "Adult child", "description": "Adult child of the household", "created_at": now, "updated_at": now},
        ],
    )


def downgrade() -> None:
    # Remove role codes added
    op.execute(sa.text("DELETE FROM role_codes WHERE code IN ('HOOFDLID', 'PARTNER', 'KIND')"))
    # Remove "U" gender code
    op.execute(sa.text("DELETE FROM gender_codes WHERE code = 'U'"))
    # Remove English translations added
    op.execute(sa.text("DELETE FROM gender_codes WHERE code IN ('M','F','X') AND language = 'en'"))
    # Revert X -> O
    op.execute(
        sa.text("UPDATE gender_codes SET code = 'O', value = 'Onzijdig', description = 'Neutraal geslacht' WHERE code = 'X'")
    )

    op.drop_constraint("fk_members_board_member_id", "members", type_="foreignkey")
    op.drop_column("members", "board_member_id")
    op.drop_column("persons", "mobile")
