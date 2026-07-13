"""Fase 4b (#403): workflow-definities + instanties; berichten-definitie geseed

Revision ID: 082
Revises: 081
"""
from alembic import op
import sqlalchemy as sa

revision = "082"
down_revision = "081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    has_def = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'workflow' "
        "AND table_name = 'workflow_definitions'")).scalar()
    if not has_def:
        op.create_table(
            "workflow_definitions",
            sa.Column("code", sa.String(50), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("steps", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            schema="workflow",
        )
        op.create_table(
            "workflow_instances",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("definition_code", sa.String(50), nullable=False, index=True),
            sa.Column("subject_type", sa.String(50), nullable=False),
            sa.Column("subject_id", sa.Integer(), nullable=False),
            sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(10), nullable=False, server_default="running"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
            schema="workflow",
        )
    has_col = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'workflow' "
        "AND table_name = 'workflow_tasks' AND column_name = 'instance_id'")).scalar()
    if not has_col:
        op.add_column("workflow_tasks",
                      sa.Column("instance_id", sa.Integer(),
                                sa.ForeignKey("workflow.workflow_instances.id"),
                                nullable=True),
                      schema="workflow")
        op.create_index("ix_workflow_tasks_instance_id", "workflow_tasks",
                        ["instance_id"], schema="workflow")
    # Seed: de berichten-workflow (P-blok-kern, veralgemeend). Idempotent.
    op.execute("""
        INSERT INTO workflow.workflow_definitions (code, name, steps)
        VALUES ('bericht', 'Bericht behartigen',
                '[{"kind": "bericht.behartigen", "title": "Bericht van {afzender} behartigen", "role": "ADMIN"}]')
        ON CONFLICT (code) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("ix_workflow_tasks_instance_id", "workflow_tasks", schema="workflow")
    op.drop_column("workflow_tasks", "instance_id", schema="workflow")
    op.drop_table("workflow_instances", schema="workflow")
    op.drop_table("workflow_definitions", schema="workflow")
