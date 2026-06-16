"""FINANCE-rol toevoegen + toekennen aan de penningmeesters

Financiële scheiding: enkel FINANCE mag betalingen invullen, bewerken,
terugbetalen of verwijderen; ADMIN mag betalingen wél inkijken. De rol wordt
toegekend aan dezelfde personen als de bestaande admin-seed (migration 014).

Revision ID: 056
Revises: 055
"""
from alembic import op
import sqlalchemy as sa

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None

FINANCE_EMAILS = [
    "koen.renders@gmail.com",
    "steven.paepen@ik.me",
]


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO role_codes (code, language, value, description, created_at, updated_at) "
        "VALUES ('FINANCE', 'nl', 'Penningmeester', "
        "'Beheert betalingen: invullen, bewerken, terugbetalen', now(), now()) "
        "ON CONFLICT (code) DO NOTHING"
    ))
    for email in FINANCE_EMAILS:
        row = conn.execute(
            sa.text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        ).fetchone()
        if row:
            user_id = row[0]
        else:
            user_id = conn.execute(
                sa.text(
                    "INSERT INTO users (email, is_active, created_at, updated_at) "
                    "VALUES (:email, true, now(), now()) RETURNING id"
                ),
                {"email": email},
            ).fetchone()[0]
        conn.execute(
            sa.text(
                "INSERT INTO user_roles (user_id, role_code, created_at) "
                "VALUES (:user_id, 'FINANCE', now()) ON CONFLICT DO NOTHING"
            ),
            {"user_id": user_id},
        )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM user_roles WHERE role_code = 'FINANCE'"))
    conn.execute(sa.text("DELETE FROM role_codes WHERE code = 'FINANCE'"))
