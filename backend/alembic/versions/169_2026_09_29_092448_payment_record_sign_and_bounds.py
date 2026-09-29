"""The rules of a payment record at rest (CR-13 phase 2, #1249, §B5.2).

`PaymentRecord.check()` refuses, on every flush, a charge that is not positive, a
refund that is not negative, and a paid amount outside the record's amount. The
database says the same about one row, so it says it too (§B4.2):

- **the sign rule, on living rows only** — `deleted_at IS NOT NULL OR (charge and
  amount > 0) OR (refund and amount < 0)`. A soft-deleted row is still a row; the
  same pattern as a partial UNIQUE under soft delete (master CLI, 28 September 2026);
- **the bounds of what came in, on all rows** — a charge between 0 and its amount,
  a refund between its amount and 0 (#146, #219).

**Why this is safe although it is not additive** (#1255; Koen, 28 September 2026:
"a + b allebei in v2.8.0", then "Ja, regel databank ook in v2.8"). The old app
could leave a charge of 0,00: `reconcile_charges` closed a charge on what came in,
and when nothing had come in that was 0,00 — the trap #673 named. Since phase 2 it
removes such a record instead (rule (b)), leaving `amount` as it was. This
migration does the same, first, to every living record of 0,00 already there: it
soft-deletes it, writes a history row (`source="migration"`,
`action="zero_charge_removed"`) and reports the count. Only then do the two CHECKs
go on. `docker compose up` replaces the container, so the old app writes nothing
while the new one migrates.

What it cannot fix it refuses: a living record with the wrong sign that is not 0,00,
or a paid amount outside its record — counted and named, and nothing changed. None
existed when this was measured, on any environment.

Going back to v2.7.0 after this migration means the dump (#1203).
"""

import logging

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
revision = "169_2026_09_29_092448"
down_revision = "169_2026_09_29_090415"
branch_labels = None
depends_on = None

#: #1255: this migration declares what it is. A clean-up and constraints on
#: existing columns.
ADDITIVE = False

log = logging.getLogger("alembic.runtime.migration")

TABLE = "payment.payment_records"
SIGN = "ck_payment_records_sign"
BOUNDS = "ck_payment_records_amount_paid_bounds"

SIGN_CHECK = (
    "deleted_at IS NOT NULL OR (type = 'charge' AND amount > 0) OR (type = 'refund' AND amount < 0)"
)
BOUNDS_CHECK = (
    "amount_paid IS NULL OR (type = 'charge' AND amount_paid BETWEEN 0 AND amount) "
    "OR (type = 'refund' AND amount_paid BETWEEN amount AND 0)"
)

#: A living record of nothing: what `reconcile_charges` could leave behind.
ZERO = "deleted_at IS NULL AND amount = 0"
#: A living record with the wrong sign that is not 0,00: nothing produces it, so a
#: row like that is a question for a person, not for this migration.
WRONG_SIGN = f"deleted_at IS NULL AND amount <> 0 AND NOT ({SIGN_CHECK})"
#: What came in outside the record, on any row.
OUT_OF_BOUNDS = f"NOT ({BOUNDS_CHECK})"


class DataCheckFailed(RuntimeError):
    """Rows this migration cannot correct: fix them first, then migrate again."""


def _count(conn, where: str) -> int:
    return conn.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE {where}")).scalar()


def _has_check(conn, name: str) -> bool:
    checks = sa.inspect(conn).get_check_constraints("payment_records", schema="payment")
    return any(check["name"] == name for check in checks)


def data_check(conn) -> list[str]:
    """What this migration refuses to touch, with its count."""
    problems = []
    wrong_sign = _count(conn, WRONG_SIGN)
    if wrong_sign:
        problems.append(f"{wrong_sign} living payment record(s) with the wrong sign")
    out_of_bounds = _count(conn, OUT_OF_BOUNDS)
    if out_of_bounds:
        problems.append(f"{out_of_bounds} payment record(s) paid beyond their amount")
    return problems


def remove_zero_records(conn) -> int:
    """Soft-delete every living record of 0,00, with a history row each (rule (b))."""
    ids = [row[0] for row in conn.execute(sa.text(f"SELECT id FROM {TABLE} WHERE {ZERO}"))]
    if not ids:
        return 0
    conn.execute(
        sa.text(
            """
            INSERT INTO payment.payment_record_history (
                tenant_id, operation, action, source, actor, recorded_at,
                payment_record_id, payable_type, payable_id, amount, amount_paid,
                method, status, type, refund_of_id, gateway_payment_id, note, paid_at
            )
            SELECT tenant_id, 'delete', 'zero_charge_removed', 'migration', NULL, now(),
                   id, payable_type, payable_id, amount, amount_paid,
                   method, status, type, refund_of_id, gateway_payment_id, note, paid_at
            FROM payment.payment_records
            WHERE id = ANY(:ids)
            """
        ),
        {"ids": ids},
    )
    conn.execute(
        sa.text(f"UPDATE {TABLE} SET deleted_at = now() WHERE id = ANY(:ids)"), {"ids": ids}
    )
    return len(ids)


def upgrade() -> None:
    conn = op.get_bind()
    problems = data_check(conn)
    if problems:
        raise DataCheckFailed(
            "CR-13 phase 2 cannot put its constraints on rows that break them: "
            + "; ".join(problems)
            + ". Correct those records on the payments screen, then deploy again. "
            "Nothing was changed."
        )
    removed = remove_zero_records(conn)
    log.info("CR-13 phase 2: %d payment record(s) of 0,00 removed (zero_charge_removed)", removed)
    if not _has_check(conn, SIGN):
        op.create_check_constraint(SIGN, "payment_records", SIGN_CHECK, schema="payment")
    if not _has_check(conn, BOUNDS):
        op.create_check_constraint(BOUNDS, "payment_records", BOUNDS_CHECK, schema="payment")


def downgrade() -> None:
    # Schema only: the two CHECKs go. The records of 0,00 this migration removed stay
    # removed — soft-deleted, with their history row, which says what they were.
    conn = op.get_bind()
    for name in (BOUNDS, SIGN):
        if _has_check(conn, name):
            op.drop_constraint(name, "payment_records", type_="check", schema="payment")
