"""Workflow-embryo (#398): schema 'workflow' + workflow_tasks

Revision ID: 072
Revises: 071
"""
from alembic import op
import sqlalchemy as sa

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS workflow")
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'workflow' AND table_name = 'workflow_tasks'")).scalar()
    if exists:
        return
    op.create_table(
        "workflow_tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("subject_type", sa.String(50), nullable=False),
        sa.Column("subject_id", sa.Integer, nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("required_role", sa.String(20), nullable=False, server_default="ADMIN"),
        sa.Column("decision", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_by", sa.String(255), nullable=True),
        schema="workflow",
    )
    op.create_index("ix_workflow_tasks_status", "workflow_tasks", ["status"], schema="workflow")
    op.create_index("ix_workflow_tasks_kind", "workflow_tasks", ["kind"], schema="workflow")


def downgrade() -> None:
    op.drop_table("workflow_tasks", schema="workflow")
