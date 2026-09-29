"""A circle relation cannot start after it ends (#1346).

Since #1346 the secretary chooses the start date on the circle screen, and can
change it afterwards. `OrganizationPerson.check()` refuses a start after the end
on every flush; this migration says the same at rest, so a script or a bulk update
cannot store it either.

`start_date <= end_date`, not `<`: someone added and taken out again on the same
day has start = end, and that must stay possible. Both ends stay optional.

**Not additive** (#1255): a constraint on existing columns. Safe for the old app,
reasoned from its writers: `add_to_circle` starts a relation today, and
`end_circle_relation` ends it today or later, so it cannot write a start after the
end. The migration counts the rows that break the rule before it adds it,
soft-deleted rows included (the CHECK holds for them too), and stops with a
message instead of skipping. Measured on PROD by the master CLI before the build:
2 rows, neither ended.
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
revision = "174_2026_09_29_193211"
down_revision = "173_2026_09_29_175443"
branch_labels = None
depends_on = None


#: #1255: this migration declares what it is. A constraint on existing columns.
ADDITIVE = False

NAME = "ck_organization_persons_period"
CHECK = "start_date IS NULL OR end_date IS NULL OR start_date <= end_date"
#: The rows that break it. No `deleted_at` filter: a soft-deleted row is a row.
VIOLATES = "start_date > end_date"


class DataCheckFailed(RuntimeError):
    """Rows that would violate the constraint: fix them first, then migrate again."""


def _has_check(conn) -> bool:
    checks = sa.inspect(conn).get_check_constraints("organization_persons", schema="mdm")
    return any(check["name"] == NAME for check in checks)


def upgrade() -> None:
    conn = op.get_bind()
    n = conn.execute(
        sa.text(f"SELECT COUNT(*) FROM mdm.organization_persons WHERE {VIOLATES}")
    ).scalar()
    if n:
        raise DataCheckFailed(
            f"{n} row(s) in mdm.organization_persons start after they end, which "
            f"{NAME} forbids. Correct their dates on the circle screen, then deploy "
            "again. Nothing was changed."
        )
    if not _has_check(conn):
        op.create_check_constraint(NAME, "organization_persons", CHECK, schema="mdm")


def downgrade() -> None:
    # Schema only: the CHECK goes. No data is touched, and none was changed.
    conn = op.get_bind()
    if _has_check(conn):
        op.drop_constraint(NAME, "organization_persons", type_="check", schema="mdm")
