"""email_log + form engine (#328, #327)

Twee losse modules in één migratie:
- ``email_log``: centrale log van alle uitgaande mails (geschreven vanuit het
  choke point in app/services/email.py). Geen FK's — losgekoppeld.
- form engine: ``forms`` + ``form_fields`` + ``form_field_options`` +
  ``form_submissions`` + ``form_submission_answers``. Volledig genormaliseerd
  (geen JSON), geen FK's naar Person/Member/Activity.

Idempotent (bestaanschecks) zodat een herhaalde upgrade niet faalt.

Revision ID: 062
Revises: 061
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _has_table("email_log"):
        op.create_table(
            "email_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("recipient", sa.String(length=255), nullable=False),
            sa.Column("subject", sa.String(length=500), nullable=False),
            sa.Column("email_type", sa.String(length=40), nullable=False, server_default="other"),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="sent"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_email_log_created_at", "email_log", ["created_at"])
        op.create_check_constraint(
            "ck_email_log_status", "email_log",
            "status IN ('sent', 'failed', 'skipped')",
        )

    if not _has_table("forms"):
        op.create_table(
            "forms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("slug", sa.String(length=200), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("share_token", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("requires_login", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("max_submissions", sa.Integer(), nullable=True),
            sa.Column("send_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("confirmation_message", sa.Text(), nullable=True),
            sa.Column("allow_edit", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_forms_share_token", "forms", ["share_token"], unique=True)
        op.create_check_constraint(
            "ck_forms_status", "forms",
            "status IN ('draft', 'open', 'closed')",
        )

    if not _has_table("form_fields"):
        op.create_table(
            "form_fields",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("form_id", sa.Integer(), sa.ForeignKey("forms.id", ondelete="CASCADE"), nullable=False),
            sa.Column("field_type", sa.String(length=20), nullable=False),
            sa.Column("label", sa.String(length=300), nullable=False),
            sa.Column("help_text", sa.Text(), nullable=True),
            sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("min_value", sa.Numeric(12, 2), nullable=True),
            sa.Column("max_value", sa.Numeric(12, 2), nullable=True),
            sa.Column("min_length", sa.Integer(), nullable=True),
            sa.Column("max_length", sa.Integer(), nullable=True),
            sa.Column("regex_pattern", sa.Text(), nullable=True),
        )
        op.create_index("ix_form_fields_form_id", "form_fields", ["form_id"])
        op.create_check_constraint(
            "ck_form_fields_type", "form_fields",
            "field_type IN ('text', 'textarea', 'number', 'email', 'select', 'radio', 'checkbox', 'rating')",
        )

    if not _has_table("form_field_options"):
        op.create_table(
            "form_field_options",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("field_id", sa.Integer(), sa.ForeignKey("form_fields.id", ondelete="CASCADE"), nullable=False),
            sa.Column("label", sa.String(length=300), nullable=False),
            sa.Column("value", sa.String(length=300), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index("ix_form_field_options_field_id", "form_field_options", ["field_id"])

    if not _has_table("form_submissions"):
        op.create_table(
            "form_submissions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("form_id", sa.Integer(), sa.ForeignKey("forms.id", ondelete="CASCADE"), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("submitter_name", sa.String(length=200), nullable=True),
            sa.Column("submitter_email", sa.String(length=255), nullable=True),
            sa.Column("edit_token", sa.String(length=64), nullable=True),
        )
        op.create_index("ix_form_submissions_form_id", "form_submissions", ["form_id"])
        op.create_index("ix_form_submissions_edit_token", "form_submissions", ["edit_token"], unique=True)

    if not _has_table("form_submission_answers"):
        op.create_table(
            "form_submission_answers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("submission_id", sa.Integer(), sa.ForeignKey("form_submissions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("field_id", sa.Integer(), sa.ForeignKey("form_fields.id", ondelete="CASCADE"), nullable=False),
            sa.Column("value_text", sa.Text(), nullable=True),
            sa.Column("value_number", sa.Numeric(12, 2), nullable=True),
            sa.Column("value_option_id", sa.Integer(), sa.ForeignKey("form_field_options.id", ondelete="SET NULL"), nullable=True),
            sa.Column("value_rating", sa.SmallInteger(), nullable=True),
        )
        op.create_index("ix_form_submission_answers_submission_id", "form_submission_answers", ["submission_id"])
        op.create_index("ix_form_submission_answers_field_id", "form_submission_answers", ["field_id"])
        op.create_check_constraint(
            "ck_form_answer_rating_range", "form_submission_answers",
            "value_rating IS NULL OR (value_rating BETWEEN 1 AND 5)",
        )


def downgrade():
    for tbl in (
        "form_submission_answers",
        "form_submissions",
        "form_field_options",
        "form_fields",
        "forms",
        "email_log",
    ):
        if _has_table(tbl):
            op.drop_table(tbl)
