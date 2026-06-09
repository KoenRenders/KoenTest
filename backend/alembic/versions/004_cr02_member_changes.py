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

    # --- Gender codes: rename "O" -> "X", add U (Onbekend) and EN translations ---
    op.execute(sa.text("UPDATE gender_codes SET code = 'X', value = 'X', description = 'X' WHERE code = 'O'"))

    op.execute(sa.text("""
        INSERT INTO gender_codes (code, language, value, description, created_at, updated_at)
        VALUES
            ('M', 'en', 'Male',    'Male gender',    now(), now()),
            ('F', 'en', 'Female',  'Female gender',  now(), now()),
            ('X', 'en', 'X',       'X',              now(), now()),
            ('U', 'nl', 'Onbekend','Onbekend geslacht', now(), now()),
            ('U', 'en', 'Unknown', 'Unknown gender', now(), now())
        ON CONFLICT DO NOTHING
    """))

    # --- Role codes: add HOOFDLID, PARTNER, KIND ---
    op.execute(sa.text("""
        INSERT INTO role_codes (code, language, value, description, created_at, updated_at)
        VALUES
            ('HOOFDLID', 'nl', 'Hoofdlid',         'Hoofdlid van het gezin',              now(), now()),
            ('HOOFDLID', 'en', 'Primary member',   'Primary member of the household',     now(), now()),
            ('PARTNER',  'nl', 'Partner',           'Partner van het hoofdlid',            now(), now()),
            ('PARTNER',  'en', 'Partner',           'Partner of the primary member',       now(), now()),
            ('KIND',     'nl', '(Meerderjarig) kind','Meerderjarig kind van het gezin',   now(), now()),
            ('KIND',     'en', 'Adult child',       'Adult child of the household',        now(), now())
        ON CONFLICT DO NOTHING
    """))


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
