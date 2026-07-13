"""kernel_jobs — achtergrondwerk-primitief (#396, §5.8)

Revision ID: 070
Revises: 069
"""
from alembic import op
import sqlalchemy as sa

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'kernel_jobs'"
    )).scalar()
    if exists:
        return
    op.create_table(
        "kernel_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="5"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_kernel_jobs_name", "kernel_jobs", ["name"])
    op.create_index("ix_kernel_jobs_status", "kernel_jobs", ["status"])
    op.create_index("ix_kernel_jobs_run_at", "kernel_jobs", ["run_at"])


def downgrade() -> None:
    op.drop_table("kernel_jobs")
