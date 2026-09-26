"""activities vocabularies become code lists

CR-12 phase 4, the activities domain. Two lists.

**`registration_type` moves out of `public`.** `public.registration_type_codes`
has existed since migration 001 with two rows, `INDIVIDUAL` and `FAMILY`, one
language per row. Migration 081 dropped the keys from the two columns that store
the type, because §8 forbids a key across schemas, and since then nothing
checked those columns. The list now lives in `activities`, both columns get
their key back, and the orphan in `public` goes.

**This DROPS an object the previous release still maps**: the ORM model of
`public.registration_type_codes`. Measured: nothing queries it — the model was
only declared — so an image rollback to the previous release still runs on
this schema. Before the drop the migration checks that the table holds no code
outside the two it knows; if it does, it stops rather than lose one.

**`registration_state` is derived** (§B5.3 note 5): open, closed, past or
cancelled, computed and never stored. A code table and labels, no key.

No data change.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.activities.codes import (
    REGISTRATION_STATE_CODES,
    REGISTRATION_TYPE_CODES,
)
from app.kernel.codes import create_code_list


# The id is a timestamp, not a sequence number (#951).
revision = '161_2026_09_26_130003'
down_revision = '160_2026_09_26_124129'
branch_labels = None
depends_on = None

TYPE_COLUMNS = ("activities.registrations.registration_type",
                "activities.activity_sub_registrations.registration_type_code")


def _has_table(schema: str, table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table, schema=schema)


def upgrade() -> None:
    bind = op.get_bind()
    create_code_list(op, schema="activities", name="registration_type",
                     codes=REGISTRATION_TYPE_CODES, fk_from=TYPE_COLUMNS,
                     code_length=10)
    create_code_list(op, schema="activities", name="registration_state",
                     codes=REGISTRATION_STATE_CODES, code_length=10)

    if _has_table("public", "registration_type_codes"):
        known = {seed.code for seed in REGISTRATION_TYPE_CODES}
        held = {row[0] for row in bind.execute(sa.text(
            "SELECT DISTINCT code FROM public.registration_type_codes")).all()}
        unknown = sorted(held - known)
        if unknown:
            raise RuntimeError(
                f"161: public.registration_type_codes holds code(s) the new list "
                f"does not know: {unknown}. Add them to REGISTRATION_TYPE_CODES "
                f"before dropping the table, or they are lost.")
        print(f"[CR-12 phase 4] public.registration_type_codes held "
              f"{sorted(held)}; all known — dropping the orphan")
        op.drop_table("registration_type_codes", schema="public")


def downgrade() -> None:
    # Schema only. The orphan comes back with the two rows it held — the
    # upgrade refused to drop it while it held anything else.
    op.create_table(
        "registration_type_codes",
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("code", "language"),
        sa.UniqueConstraint("code", name="uq_registration_type_codes_code"),
        schema="public",
    )
    op.execute("INSERT INTO public.registration_type_codes (code, language, value) "
               "VALUES ('INDIVIDUAL', 'nl', 'Individueel'), ('FAMILY', 'nl', 'Gezin')")
    for column in TYPE_COLUMNS:
        _schema, table, column_name = column.split(".")
        op.drop_constraint(f"fk_{table}_{column_name}_code", table,
                           schema="activities", type_="foreignkey")
    for name in ("registration_state", "registration_type"):
        op.drop_table(f"{name}_labels", schema="activities")
        op.drop_table(f"{name}_codes", schema="activities")
