"""Seed admin users: koen.renders@gmail.com, steven.paepen@ik.me, kris.vandenbosch@raakvzw.be

Revision ID: 014
Revises: 013
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None

ADMIN_EMAILS = [
    "koen.renders@gmail.com",
    "steven.paepen@ik.me",
    "kris.vandenbosch@raakvzw.be",
]


def upgrade():
    conn = op.get_bind()
    for email in ADMIN_EMAILS:
        result = conn.execute(
            sa.text("SELECT id FROM users WHERE email = :email"),
            {"email": email},
        ).fetchone()
        if result:
            user_id = result[0]
        else:
            result = conn.execute(
                sa.text(
                    "INSERT INTO users (email, is_active, created_at, updated_at) "
                    "VALUES (:email, true, now(), now()) RETURNING id"
                ),
                {"email": email},
            )
            user_id = result.fetchone()[0]

        conn.execute(
            sa.text(
                "INSERT INTO user_roles (user_id, role_code, created_at) "
                "VALUES (:user_id, 'ADMIN', now()) "
                "ON CONFLICT DO NOTHING"
            ),
            {"user_id": user_id},
        )


def downgrade():
    conn = op.get_bind()
    for email in ADMIN_EMAILS:
        conn.execute(sa.text(
            "DELETE FROM user_roles WHERE user_id = (SELECT id FROM users WHERE email = :email) AND role_code = 'ADMIN'"
        ), {"email": email})
