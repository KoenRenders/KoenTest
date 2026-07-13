"""Blok P deel 2 (#398): ideas → berichten-inzendingen; ideas-tabel weg

Elke idee wordt een inzending op het geseede 'berichten'-formulier (datum
behouden); onbehandelde ideeën krijgen een open behartigen-taak. Daarna
verdwijnt de ideas-tabel — berichten ís het contactkanaal.

Revision ID: 074
Revises: 073
"""
from alembic import op
import sqlalchemy as sa

revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    has_ideas = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'ideas'")).scalar()
    if not has_ideas:
        return
    form_id = bind.execute(sa.text("SELECT id FROM form.forms WHERE slug = 'berichten'")).scalar()
    field_id = bind.execute(sa.text(
        "SELECT id FROM form.form_fields WHERE form_id = :f ORDER BY position LIMIT 1"),
        {"f": form_id}).scalar()

    ideas = bind.execute(sa.text(
        "SELECT id, submitter_name, submitter_email, content, submitted_at, is_reviewed "
        "FROM ideas ORDER BY id")).fetchall()
    for idea in ideas:
        sub_id = bind.execute(sa.text("""
            INSERT INTO form.form_submissions (form_id, submitted_at, submitter_name, submitter_email)
            VALUES (:f, :at, :naam, :email) RETURNING id"""),
            {"f": form_id, "at": idea.submitted_at, "naam": idea.submitter_name,
             "email": idea.submitter_email}).scalar()
        bind.execute(sa.text("""
            INSERT INTO form.form_submission_answers (submission_id, field_id, value_text)
            VALUES (:s, :fld, :txt)"""),
            {"s": sub_id, "fld": field_id, "txt": idea.content})
        if not idea.is_reviewed:
            bind.execute(sa.text("""
                INSERT INTO workflow.workflow_tasks
                    (kind, title, subject_type, subject_id, status, required_role, created_at)
                VALUES ('bericht.behartigen', :title, 'form_submission', :s, 'open', 'ADMIN', :at)"""),
                {"title": f"Bericht van {idea.submitter_name or 'onbekende afzender'} behartigen",
                 "s": sub_id, "at": idea.submitted_at})

    op.drop_table("ideas")


def downgrade() -> None:
    # Dataverhuis is niet omkeerbaar; de tabel her-aanmaken zonder data volstaat
    # om een oudere codeversie te laten starten.
    op.create_table(
        "ideas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("submitter_name", sa.String(200), nullable=False),
        sa.Column("submitter_email", sa.String(255), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_reviewed", sa.Boolean, nullable=False, server_default="false"),
    )
