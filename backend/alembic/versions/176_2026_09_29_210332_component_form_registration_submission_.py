"""A component can ask questions, and a registration can hold the answers (CR-14 phase 2, #1333).

The board used to ask its extra questions — the Sint's time slots, the story, the
remarks — outside the platform, and had to match the answers to the registrations
by hand. A component now points at a form of the form builder, and a registration
points at the submission that holds its answers (CR-14 §B2.3).

Four new columns, and nothing existing changes meaning:

- `activities.activity_sub_registrations.form_id` — the component's questions;
- `activities.registrations.form_submission_id` — the answers. Unique among living
  registrations, the pattern CR-13 uses under soft delete: one registration per
  submission;
- `activities.registrations.answer_token` — the secret of the "answer later" link
  (§B4.8). Unique; cleared once the answers are in, so answered and still open
  cannot both be true, and the CHECK says so at rest;
- `form.form_submissions.attached` — the submission holds the answers of something
  outside the form builder. The builder refuses to delete such a submission, or a
  form that has one (§B1.1 F11), without learning what holds it.

**No foreign keys across the schemas** (#396/#397, `test_schema_boundaries`): the
two references into `form` are soft references, as `registrations.person_id` has
been since migration 078. CR-14 §B2.2 planned `SET NULL` and `RESTRICT` keys "as
`registrations.person_id` already does" — measured while building: that key was
dropped in 078, and the schema gate refuses a new one. What the keys were for is
done in code: the `attached` mark refuses the delete that `RESTRICT` would have
refused, and a component whose form is gone asks no questions.

**Additive** (#1255): new columns, nullable or with a default, no data step. The
old app never reads or writes them. The three tables were checked for CHECK
constraints on these columns: there are none, because the columns are new.
"""

import sqlalchemy as sa
from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "176_2026_09_29_210332"
down_revision = "175_2026_09_29_195535"
branch_labels = None
depends_on = None

#: #1255: this migration declares what it is. New nullable columns only.
ADDITIVE = True

SCHEMA = "activities"
COMPONENTS = "activity_sub_registrations"
REGISTRATIONS = "registrations"

UQ_SUBMISSION = "uq_registrations_form_submission_id_living"
UQ_TOKEN = "uq_registrations_answer_token"
CK_ANSWERED_OR_OPEN = "ck_registrations_answered_or_open"


def _columns(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table, schema=SCHEMA)}


def _indexes(conn, table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(conn).get_indexes(table, schema=SCHEMA)}


def _checks(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_check_constraints(table, schema=SCHEMA)}


def upgrade() -> None:
    conn = op.get_bind()

    if "form_id" not in _columns(conn, COMPONENTS):
        op.add_column(COMPONENTS, sa.Column("form_id", sa.Integer(), nullable=True), schema=SCHEMA)

    columns = _columns(conn, REGISTRATIONS)
    if "form_submission_id" not in columns:
        op.add_column(
            REGISTRATIONS,
            sa.Column("form_submission_id", sa.Integer(), nullable=True),
            schema=SCHEMA,
        )
    if "answer_token" not in columns:
        op.add_column(
            REGISTRATIONS, sa.Column("answer_token", sa.String(64), nullable=True), schema=SCHEMA
        )

    indexes = _indexes(conn, REGISTRATIONS)
    if UQ_SUBMISSION not in indexes:
        op.create_index(
            UQ_SUBMISSION,
            REGISTRATIONS,
            ["form_submission_id"],
            unique=True,
            schema=SCHEMA,
            postgresql_where=sa.text("deleted_at IS NULL AND form_submission_id IS NOT NULL"),
        )
    if UQ_TOKEN not in indexes:
        op.create_index(UQ_TOKEN, REGISTRATIONS, ["answer_token"], unique=True, schema=SCHEMA)
    if CK_ANSWERED_OR_OPEN not in _checks(conn, REGISTRATIONS):
        op.create_check_constraint(
            CK_ANSWERED_OR_OPEN,
            REGISTRATIONS,
            "form_submission_id IS NULL OR answer_token IS NULL",
            schema=SCHEMA,
        )
    submission_columns = {
        c["name"] for c in sa.inspect(conn).get_columns("form_submissions", schema="form")
    }
    if "attached" not in submission_columns:
        op.add_column(
            "form_submissions",
            sa.Column("attached", sa.Boolean(), nullable=False, server_default=sa.false()),
            schema="form",
        )


def downgrade() -> None:
    # Schema only, and it loses data: the links between registrations and their
    # answers, the components' forms, the open answer links and the `attached`
    # marks go with the columns. The submissions themselves stay.
    conn = op.get_bind()
    submission_columns = {
        c["name"] for c in sa.inspect(conn).get_columns("form_submissions", schema="form")
    }
    if "attached" in submission_columns:
        op.drop_column("form_submissions", "attached", schema="form")
    if CK_ANSWERED_OR_OPEN in _checks(conn, REGISTRATIONS):
        op.drop_constraint(CK_ANSWERED_OR_OPEN, REGISTRATIONS, type_="check", schema=SCHEMA)
    indexes = _indexes(conn, REGISTRATIONS)
    for name in (UQ_TOKEN, UQ_SUBMISSION):
        if name in indexes:
            op.drop_index(name, table_name=REGISTRATIONS, schema=SCHEMA)
    columns = _columns(conn, REGISTRATIONS)
    for column in ("answer_token", "form_submission_id"):
        if column in columns:
            op.drop_column(REGISTRATIONS, column, schema=SCHEMA)
    if "form_id" in _columns(conn, COMPONENTS):
        op.drop_column(COMPONENTS, "form_id", schema=SCHEMA)
