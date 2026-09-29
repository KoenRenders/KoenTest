"""A chosen form option cannot be deleted under its answers (#1347).

`form_submission_answers.value_option_id` was `ON DELETE SET NULL` (migration 062):
deleting an option someone chose left their answer as an empty row, which read as
"did not answer". On PROD that cost one answer on 29 September 2026. Since #1347 the
forms service refuses it (`refuse_losing_answers`); this makes the database the net
under it: `RESTRICT`, so a delete along any other way fails instead of wiping.

Checked before choosing `RESTRICT`: no writer relies on `SET NULL`.
- `delete_option` and `apply_definition` refuse first, since #1347.
- `delete_form` deletes through the ORM, and `FormSubmissionAnswer.option` is a
  mapped relationship, so the answers are deleted before the options in the
  same flush.
- `delete_submission` deletes answers, never options.

`field_id` stays `ON DELETE CASCADE`: `delete_field` refuses an answered question
in the service, and `delete_form` needs the cascade when it takes everything.

**Not additive** (#1255): the rule of an existing foreign key changes. No data
precondition: `RESTRICT` holds for every row that `SET NULL` held for.
"""

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
revision = "175_2026_09_29_195535"
down_revision = "174_2026_09_29_193211"
branch_labels = None
depends_on = None


#: #1255: this migration declares what it is. The rule of an existing key changes.
ADDITIVE = False

NAME = "form_submission_answers_value_option_id_fkey"


def _set_rule(rule: str) -> None:
    op.drop_constraint(NAME, "form_submission_answers", type_="foreignkey", schema="form")
    op.create_foreign_key(
        NAME,
        "form_submission_answers",
        "form_field_options",
        ["value_option_id"],
        ["id"],
        source_schema="form",
        referent_schema="form",
        ondelete=rule,
    )


def upgrade() -> None:
    _set_rule("RESTRICT")


def downgrade() -> None:
    # Schema only: the key goes back to SET NULL. No data is touched.
    _set_rule("SET NULL")
