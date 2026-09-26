"""the payment vocabularies become code lists

CR-12 phase 1. Five lists at once, because they cannot go one at a time: the
enums are plain, so `record.status == "paid"` turns silently false the moment a
column becomes one. Half a conversion is worse than either whole state.

Four lists live in `payment`; the fifth, the payment **method**, lives in `mdm`
because two domains store it (§B4.1) — which makes the foreign key from
`payment` and from `activities` the cross-schema one §B2.4 allows.

**The one data change of the whole change request (§B4.6).** R8 says stored
values do not change; here they do, once, and only in
`activities.registrations.payment_method`. That column and
`payment.payment_records.method` are one list in two spellings — the
duplication `CLAUDE.md` names as the bug — and the alternative, two code tables
for one list, would keep the bug and give it a foreign key.

Measured on HDEV on 26 September 2026, over the **whole** table (49 rows):
`ONLINE` 22, `OVERSCHRIJVING` 15, NULL 11, `transfer` 1. The mapping:

    ONLINE         -> online     (case)
    OVERSCHRIJVING -> transfer   (the Dutch radio value of the public form)
    transfer       -> transfer   (already the target spelling; the column is mixed)
    NULL           -> NULL       (a free registration has no method)

Three things about that, each of which would have broken this migration:

- **No `deleted_at` filter on the UPDATE.** A foreign key holds for every row in
  the table, soft-deleted ones included; `deleted_at` is a column, not a filter
  the database knows. Five rows are soft-deleted (4× `ONLINE`, 1×
  `OVERSCHRIJVING`), and an update that skipped them would leave the key to fail
  on exactly those five. The counts below are over the whole table too (AC6).
- **The writer changes in the same commit.** `_inschrijf_form.html` posted
  `OVERSCHRIJVING` as a radio value and `router.py` stored it verbatim. With the
  key in place and the form unchanged, the *next* registration by bank transfer
  would fail on the constraint.
- **There is no history to migrate.** `activities.registration_history` has no
  `payment_method` column, and the column exists in exactly one place in the
  whole schema. Verified on 26 September 2026 — noted here so the next reader
  does not go looking for a table that is not there.

Also dropped: `ck_payment_records_type`, a `CHECK (type IN ('charge','refund'))`
that says what the new foreign key says. Two places for one fact, and the
expensive half is the second: with the check still there a third payment type
would cost a row *and* a migration, so "a new value is a row" would quietly stop
being true. And `public.payment_status_codes`, an orphan since migration 001
whose rows are upper case (`PENDING`/`PAID`/`FAILED`) — not what the column
stores, and nothing reads them.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.mdm.codes import PAYMENT_METHOD_CODES
from app.domains.payment.codes import (
    PAYABLE_TYPE_CODES,
    PAYMENT_PROVIDER_CODES,
    PAYMENT_STATUS_CODES,
    PAYMENT_TYPE_CODES,
)
from app.kernel.codes import add_code_fk, create_code_list


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '153_2026_09_26_001941'
down_revision = '152_2026_09_25_230819'
branch_labels = None
depends_on = None

#: What the column holds today → what it holds afterwards. `transfer` and NULL
#: are absent on purpose: they already fit, and listing them would suggest the
#: UPDATE touches them.
METHOD_FIX = {"ONLINE": "online", "OVERSCHRIJVING": "transfer"}

METHOD_COLUMN = "activities.registrations.payment_method"


def _counts(bind, where: str = "") -> dict:
    rows = bind.execute(sa.text(
        f"SELECT payment_method AS value, count(*) AS n "
        f"FROM activities.registrations {where} GROUP BY payment_method")).all()
    return {row.value: row.n for row in rows}


def upgrade() -> None:
    bind = op.get_bind()

    # ── The payment method, in mdm ───────────────────────────────────────────
    # The list first, without its foreign keys: the data has to fit before the
    # key can go on, and the guard inside `add_code_fk` is what proves it does.
    create_code_list(op, schema="mdm", name="payment_method",
                     codes=PAYMENT_METHOD_CODES, code_length=20)

    # ── §B4.6: the one data change ───────────────────────────────────────────
    before = _counts(bind)
    print(f"[CR-12 §B4.6] {METHOD_COLUMN} before: {before}")
    for old, new in METHOD_FIX.items():
        bind.execute(sa.text(
            "UPDATE activities.registrations SET payment_method = :new "
            "WHERE payment_method = :old"), {"old": old, "new": new})
    after = _counts(bind)
    print(f"[CR-12 §B4.6] {METHOD_COLUMN} after:  {after}")
    if sum(before.values()) != sum(after.values()):
        raise RuntimeError(
            f"{METHOD_COLUMN}: {sum(before.values())} rows before and "
            f"{sum(after.values())} after — an UPDATE may not lose a row")

    # ── The foreign keys on the method ───────────────────────────────────────
    # `add_code_fk` counts what does not fit and aborts naming the values, so a
    # value the mapping above does not know (`CHEQUE`) stops the migration here
    # rather than at the constraint. That is intended behaviour: finding one on
    # HDEV is a discovery, not a failure.
    for column in ("payment.payment_records.method", METHOD_COLUMN):
        add_code_fk(op, column, "mdm", "payment_method")

    # ── The four lists of the payment domain ─────────────────────────────────
    create_code_list(op, schema="payment", name="payment_status",
                     codes=PAYMENT_STATUS_CODES,
                     fk_from=("payment.payment_records.status",), code_length=20)
    create_code_list(op, schema="payment", name="payment_type",
                     codes=PAYMENT_TYPE_CODES,
                     fk_from=("payment.payment_records.type",), code_length=20)
    create_code_list(op, schema="payment", name="payable_type",
                     codes=PAYABLE_TYPE_CODES,
                     fk_from=("payment.payment_records.payable_type",),
                     code_length=50)
    create_code_list(op, schema="payment", name="payment_provider",
                     codes=PAYMENT_PROVIDER_CODES,
                     fk_from=("payment.gateway_payments.provider",),
                     code_length=20)

    # Only after the key: until now the check was the column's only guard.
    op.drop_constraint("ck_payment_records_type", "payment_records",
                       schema="payment", type_="check")

    # The orphan. Dropped and not moved: its rows are upper case, which is not
    # what the column stores, and nothing reads them (§B5.3 note 1).
    op.drop_table("payment_status_codes")


def downgrade() -> None:
    # Reverses the schema. It does **not** reverse the data: the fifteen
    # `OVERSCHRIJVING` rows stay `transfer`, and that is deliberate — going back
    # would restore a spelling that no writer produces any more, so it would
    # break the next registration instead of repairing anything. Say it out loud
    # rather than pretend the reversal is whole.
    op.create_table(
        "payment_status_codes",
        sa.Column("code", sa.String(10), primary_key=True),
        sa.Column("language", sa.String(5), primary_key=True),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_check_constraint("ck_payment_records_type", "payment_records",
                               "type IN ('charge','refund')", schema="payment")
    for constraint, table, schema in (
        ("fk_gateway_payments_provider_code", "gateway_payments", "payment"),
        ("fk_payment_records_payable_type_code", "payment_records", "payment"),
        ("fk_payment_records_type_code", "payment_records", "payment"),
        ("fk_payment_records_status_code", "payment_records", "payment"),
        ("fk_registrations_payment_method_code", "registrations", "activities"),
        ("fk_payment_records_method_code", "payment_records", "payment"),
    ):
        op.drop_constraint(constraint, table, schema=schema, type_="foreignkey")
    for name in ("payment_provider", "payable_type", "payment_type",
                 "payment_status"):
        op.drop_table(f"{name}_labels", schema="payment")
        op.drop_table(f"{name}_codes", schema="payment")
    op.drop_table("payment_method_labels", schema="mdm")
    op.drop_table("payment_method_codes", schema="mdm")
