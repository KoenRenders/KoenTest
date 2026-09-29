"""The rules of a registration at rest (CR-13 phase 1, #757, §B5.2).

`Registration` now refuses a blank name or e-mail address itself, on every path
(its validators). The database says the same about one row, so it says it too — "if PostgreSQL can say it about one row, PostgreSQL says it"
(§B4.2): a bulk update, an import or a script that bypasses the object still
cannot store a blank. "Not blank" is two constraints: `NOT NULL`, and a CHECK on
the trimmed value, because an empty string is not NULL.

The mobile number is not among them: no database constraint on the registration
phone (Koen, 29 September 2026); the entrances still require it.

The order lines and the prices get theirs too: a quantity above zero, prices not
negative, a participant limit above zero when there is one. Some of these were
meant to exist since migration 039 (#96), but 039 skipped a constraint silently
when a row violated it — so whether they exist on a given environment was never
certain. This migration makes sure: a constraint that exists stays; one that is
missing is added after a count, and a violating row stops the migration with a
message that names the table, the rule and the count, instead of skipping.

**Not additive** (#1255): constraints on existing columns. Safe for the old app,
measured, not assumed (§B5.2): every writer of these columns refuses what they
refuse — the public form, the JSON API and the board's form through
`create_registration`, the screen that corrects a registration through
`update_registration_contact`, which since this phase also refuses a blank e-mail
address (Koen, 29 September 2026: the board can change an address, not clear
it) — and the counts of blank names and e-mail addresses were zero on every
environment before the deploy; the migration counts again, on the rows there are
when it runs.
Going back to v2.7.0 after this migration means the dump, as for every release
with a migration (#1203).
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
revision = "168_2026_09_29_073633"
down_revision = "167_2026_09_28_045715"
branch_labels = None
depends_on = None

#: #1255: this migration declares what it is. Constraints on existing columns.
ADDITIVE = False

SCHEMA = "activities"

#: The registration's contact fields that hold at rest: NOT NULL and not blank.
#: Not `phone` — required at the entrances only (Koen, 29 September 2026).
CONTACT_COLUMNS = ("contact_name", "contact_email")

#: (table, constraint, CHECK, "this row violates it", created here) — `created
#: here` is False for the ones 039 or 023 were meant to create; downgrade leaves
#: those, because on most environments they predate this migration.
CHECKS = [
    *(
        (
            "registrations",
            f"ck_registrations_{column}_not_blank",
            f"btrim({column}) <> ''",
            f"{column} IS NOT NULL AND btrim({column}) = ''",
            True,
        )
        for column in CONTACT_COLUMNS
    ),
    (
        "registration_items",
        "ck_registration_items_quantity_positive",
        "quantity > 0",
        "quantity <= 0",
        False,
    ),
    (
        "activity_products",
        "ck_activity_products_price_non_negative",
        "price >= 0",
        "price < 0",
        False,
    ),
    (
        "activity_products",
        "ck_activity_products_member_price_non_negative",
        "member_price >= 0 OR member_price IS NULL",
        "member_price < 0",
        False,
    ),
    (
        "activity_sub_registrations",
        "ck_activity_sub_registrations_price_non_negative",
        "price >= 0",
        "price < 0",
        False,
    ),
    (
        "activity_sub_registrations",
        "ck_activity_sub_registrations_member_price_non_negative",
        "member_price >= 0 OR member_price IS NULL",
        "member_price < 0",
        False,
    ),
    (
        "activity_products",
        "ck_activity_products_max_participants_positive",
        "max_participants IS NULL OR max_participants > 0",
        "max_participants <= 0",
        True,
    ),
    (
        "activity_sub_registrations",
        "ck_activity_sub_registrations_max_participants_positive",
        "max_participants IS NULL OR max_participants > 0",
        "max_participants <= 0",
        True,
    ),
]


class DataCheckFailed(RuntimeError):
    """Rows that would violate a constraint: fix them first, then migrate again."""


def _count(conn, table: str, where: str) -> int:
    return conn.execute(sa.text(f"SELECT COUNT(*) FROM {SCHEMA}.{table} WHERE {where}")).scalar()


def _has_check(conn, table: str, name: str) -> bool:
    checks = sa.inspect(conn).get_check_constraints(table, schema=SCHEMA)
    return any(check["name"] == name for check in checks)


def data_check(conn) -> list[str]:
    """Every rule this migration adds, with the rows that break it today.

    Deleted rows count too: a soft-deleted row is still a row, and a constraint
    holds for all of them (§B5.2).
    """
    problems = []
    for column in CONTACT_COLUMNS:
        n = _count(conn, "registrations", f"{column} IS NULL OR btrim({column}) = ''")
        if n:
            problems.append(f"{n} registration(s) without {column}")
    for table, name, _check, violates, _ours in CHECKS:
        if table == "registrations" or _has_check(conn, table, name):
            continue  # the contact fields are counted above, once
        n = _count(conn, table, violates)
        if n:
            problems.append(f"{n} row(s) in {SCHEMA}.{table} break {name}")
    return problems


def upgrade() -> None:
    conn = op.get_bind()
    problems = data_check(conn)
    if problems:
        raise DataCheckFailed(
            "CR-13 phase 1 cannot put its constraints on rows that break them: "
            + "; ".join(problems)
            + ". Correct those rows (the registration screen in the back office), "
            "then deploy again. Nothing was changed."
        )
    for column in CONTACT_COLUMNS:
        op.alter_column("registrations", column, nullable=False, schema=SCHEMA)
    for table, name, check, _violates, _ours in CHECKS:
        if not _has_check(conn, table, name):
            op.create_check_constraint(name, table, check, schema=SCHEMA)


def downgrade() -> None:
    # Schema only, and only what this migration introduced: the not-blank checks,
    # NOT NULL on the contact fields, and the participant limits. The price and
    # quantity checks stay — on most environments 039 or 023 created them, and
    # this migration cannot tell where it filled a gap. No data is touched.
    conn = op.get_bind()
    for table, name, _check, _violates, ours in CHECKS:
        if ours and _has_check(conn, table, name):
            op.drop_constraint(name, table, type_="check", schema=SCHEMA)
    for column in CONTACT_COLUMNS:
        op.alter_column("registrations", column, nullable=True, schema=SCHEMA)
