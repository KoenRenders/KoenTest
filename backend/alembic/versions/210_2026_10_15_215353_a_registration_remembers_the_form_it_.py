"""a registration remembers the form it came from

#1987: a registration was created once per press of its button only because the
browser greyed the button out after the first press. A phone that sends the form
again after a lost connection, or two presses on a slow line, made two
registrations — and with online payment, two payments. Since this change a shown
form carries a key (the random part of its signed token, Koen, 15 October 2026:
"a"), and the registration it makes stores it under a unique index per tenant:
the database decides, so two posts at the same moment cannot both pass a check.

Existing registrations have no key (NULL), and the index leaves those out.
Idempotent: the column and the index are made only when they are not there.
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
revision = "210_2026_10_15_215353"
down_revision = "210_2026_10_15_214414"
branch_labels = None
depends_on = None

INDEX = "uq_registrations_submission_key"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE activities.registrations ADD COLUMN IF NOT EXISTS submission_key VARCHAR(64)"
    )
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} "
        "ON activities.registrations (tenant_id, submission_key) "
        "WHERE submission_key IS NOT NULL"
    )


def downgrade() -> None:
    # Schema and data: the keys are dropped with their column. A registration
    # loses nothing it needs; only a repeat of a form shown before the downgrade
    # is no longer recognised.
    op.execute(f"DROP INDEX IF EXISTS activities.{INDEX}")
    op.execute("ALTER TABLE activities.registrations DROP COLUMN IF EXISTS submission_key")
