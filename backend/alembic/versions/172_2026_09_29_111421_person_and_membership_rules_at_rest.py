"""The rules of a person and a membership at rest (CR-13 phase 3, #1250, §B5.2).

A person always has a name, and a membership cannot end before it begins. The
objects say so on every ORM path since this phase (`Person`'s validators,
`Membership.check()`); the database says it too, so a bulk update, an import or a
script that bypasses the objects cannot store it either — "if PostgreSQL can say it
about one row, PostgreSQL says it" (§B4.2).

The names are `NOT NULL` already (since the first schema); what was missing is
"not blank": an empty or all-space string is not NULL. A membership's period stays
optional — a membership without dates exists (the import writes one) — so the
CHECK only speaks when both ends are there.

Deliberately **no** constraint on `date_of_birth` or `gender_code`: the rule that
requires them (#681) is a rule about a person *in a household*, not about a person —
`create_person_for_circle` (#939) creates persons from the meeting circle without
either, on purpose. Its home is the household link, in code (§B5.2).

The third constraint of this phase, one primary contact per person and type, is not
here because it exists: `uq_contact_details_one_primary_per_type`, migration 053,
partial on `is_primary = true AND deleted_at IS NULL` — present on PROD, measured.

**Not additive** (#1255): constraints on existing columns. Safe for the old app,
measured, not assumed (§B5.2): every writer of a membership derives both dates from
one year or one date, and every form that writes a person's name requires it; the
counts were zero on every environment before the deploy (blank names, a period that
ends before it begins). The migration counts again, on the rows there are when it
runs, and stops with a message instead of skipping.
Going back to v2.7.0 after this migration means the dump, as for every release with
a migration (#1203).
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
revision = "172_2026_09_29_111421"
down_revision = "171_2026_09_29_102827"
branch_labels = None
depends_on = None

#: #1255: this migration declares what it is. Constraints on existing columns.
ADDITIVE = False

#: (schema, table, constraint, CHECK, "this row violates it"). Deleted rows count
#: too: a soft-deleted row is still a row, and these hold for all of them.
CHECKS = [
    *(
        (
            "mdm",
            "persons",
            f"ck_persons_{column}_not_blank",
            f"btrim({column}) <> ''",
            f"{column} IS NULL OR btrim({column}) = ''",
        )
        for column in ("first_name", "last_name")
    ),
    (
        "membership",
        "memberships",
        "ck_memberships_valid_period",
        "valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to",
        "valid_from > valid_to",
    ),
]


class DataCheckFailed(RuntimeError):
    """Rows that would violate a constraint: fix them first, then migrate again."""


def _has_check(conn, schema: str, table: str, name: str) -> bool:
    checks = sa.inspect(conn).get_check_constraints(table, schema=schema)
    return any(check["name"] == name for check in checks)


def data_check(conn) -> list[str]:
    """Every rule this migration adds, with the rows that break it today."""
    problems = []
    for schema, table, name, _check, violates in CHECKS:
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {schema}.{table} WHERE {violates}")).scalar()
        if n:
            problems.append(f"{n} row(s) in {schema}.{table} break {name}")
    return problems


def upgrade() -> None:
    conn = op.get_bind()
    problems = data_check(conn)
    if problems:
        raise DataCheckFailed(
            "CR-13 phase 3 cannot put its constraints on rows that break them: "
            + "; ".join(problems)
            + ". Correct those rows (the member screens in the back office), "
            "then deploy again. Nothing was changed."
        )
    for schema, table, name, check, _violates in CHECKS:
        if not _has_check(conn, schema, table, name):
            op.create_check_constraint(name, table, check, schema=schema)


def downgrade() -> None:
    # Schema only: the three CHECKs go. No data is touched, and none was changed.
    conn = op.get_bind()
    for schema, table, name, _check, _violates in CHECKS:
        if _has_check(conn, schema, table, name):
            op.drop_constraint(name, table, type_="check", schema=schema)
