"""Add relation_type_codes table, migrate member_persons.relation_type, clean role_codes

Revision ID: 017
Revises: 016
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create relation_type_codes table
    op.create_table(
        "relation_type_codes",
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("code", "language"),
        sa.UniqueConstraint("code", name="uq_relation_type_codes_code"),
    )

    op.execute(sa.text("""
        INSERT INTO relation_type_codes (code, language, value, description, created_at, updated_at)
        VALUES
            ('HOOFDLID', 'nl', 'Hoofdlid',            'Hoofdlid van het gezin',              now(), now()),
            ('HOOFDLID', 'en', 'Primary member',       'Primary member of the household',     now(), now()),
            ('PARTNER',  'nl', 'Partner',              'Partner van het hoofdlid',            now(), now()),
            ('PARTNER',  'en', 'Partner',              'Partner of the primary member',       now(), now()),
            ('KIND',     'nl', '(Meerderjarig) kind',  'Meerderjarig kind van het gezin',    now(), now()),
            ('KIND',     'en', 'Adult child',          'Adult child of the household',        now(), now())
        ON CONFLICT DO NOTHING
    """))

    # Migrate existing member_persons data to uppercase codes
    op.execute(sa.text("""
        UPDATE member_persons SET relation_type = 'HOOFDLID'
        WHERE LOWER(relation_type) = 'hoofdlid'
    """))
    op.execute(sa.text("""
        UPDATE member_persons SET relation_type = 'PARTNER'
        WHERE LOWER(relation_type) = 'partner'
    """))
    op.execute(sa.text("""
        UPDATE member_persons SET relation_type = 'KIND'
        WHERE LOWER(relation_type) IN ('(meerderjarig) kind', 'kind')
    """))

    # Resize column and add FK
    with op.batch_alter_table("member_persons") as batch_op:
        batch_op.alter_column("relation_type",
            existing_type=sa.String(30),
            type_=sa.String(10),
            server_default="HOOFDLID",
        )
        batch_op.create_foreign_key(
            "fk_member_persons_relation_type",
            "relation_type_codes", ["relation_type"], ["code"],
        )

    # Remove relation type codes from role_codes (they now have their own table)
    op.execute(sa.text("DELETE FROM role_codes WHERE code IN ('HOOFDLID', 'PARTNER', 'KIND')"))


def downgrade() -> None:
    # Restore relation types in role_codes
    op.execute(sa.text("""
        INSERT INTO role_codes (code, language, value, description, created_at, updated_at)
        VALUES
            ('HOOFDLID', 'nl', 'Hoofdlid',           'Hoofdlid van het gezin',              now(), now()),
            ('HOOFDLID', 'en', 'Primary member',      'Primary member of the household',     now(), now()),
            ('PARTNER',  'nl', 'Partner',             'Partner van het hoofdlid',            now(), now()),
            ('PARTNER',  'en', 'Partner',             'Partner of the primary member',       now(), now()),
            ('KIND',     'nl', '(Meerderjarig) kind', 'Meerderjarig kind van het gezin',    now(), now()),
            ('KIND',     'en', 'Adult child',         'Adult child of the household',        now(), now())
        ON CONFLICT DO NOTHING
    """))

    with op.batch_alter_table("member_persons") as batch_op:
        batch_op.drop_constraint("fk_member_persons_relation_type", type_="foreignkey")
        batch_op.alter_column("relation_type",
            existing_type=sa.String(10),
            type_=sa.String(30),
            server_default="hoofdlid",
        )

    # Migrate back to lowercase
    op.execute(sa.text("UPDATE member_persons SET relation_type = 'hoofdlid' WHERE relation_type = 'HOOFDLID'"))
    op.execute(sa.text("UPDATE member_persons SET relation_type = 'partner' WHERE relation_type = 'PARTNER'"))
    op.execute(sa.text("UPDATE member_persons SET relation_type = '(meerderjarig) kind' WHERE relation_type = 'KIND'"))

    op.drop_table("relation_type_codes")
