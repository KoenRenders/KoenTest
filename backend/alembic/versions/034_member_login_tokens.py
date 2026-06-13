"""member login tokens (email-based, no user row)

Revision ID: 034
Revises: 033
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    if "login_tokens" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("login_tokens")}
    # Lidlogins hangen niet aan een User-rij (geen admin-account): user_id mag
    # leeg zijn en het e-mailadres wordt rechtstreeks op de token bewaard.
    if "email" not in cols:
        op.add_column("login_tokens", sa.Column("email", sa.String(255), nullable=True))
    op.alter_column("login_tokens", "user_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    op.alter_column("login_tokens", "user_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("login_tokens", "email")
