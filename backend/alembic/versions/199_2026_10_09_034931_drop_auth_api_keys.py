"""drop auth api_keys

The table held the hashed keys of machine consumers (§19.3, migration 077). No
route ever depended on the guard that read it, and the three JSON routes that
managed it had no caller: CR-13 phase 4b (#1251) took the routes, the guard and
the bearer stack out. Measured on 9 October 2026 before this was written: the
table holds no row on PROD, UAT or HDEV. A table nothing reads and nothing
writes is taken out in the release that takes its code out (Koen's choice for
CR-19 and CR-20: one release, with the pre-deploy dump as the net) — left
standing, it is what nobody dares to remove a year later.
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
revision = "199_2026_10_09_034931"
down_revision = "198_2026_10_07_172748"
branch_labels = None
depends_on = None


def _table_exists(bind) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'auth' AND table_name = 'api_keys'"
            )
        ).scalar()
    )


def drop_if_empty(bind) -> bool:
    """Drop `auth.api_keys` when it is there and holds no row; says whether it did.
    A row is a refusal, not a loss: the deploy stops and somebody asks."""
    if not _table_exists(bind):
        return False  # already gone: nothing to do
    rows = bind.execute(sa.text("SELECT count(*) FROM auth.api_keys")).scalar()
    if rows:
        # It was empty everywhere when this was written. A key that exists now
        # was made by someone, for something: that is a question, not a row to
        # throw away.
        raise RuntimeError(
            f"auth.api_keys holds {rows} row(s); this migration drops the table only when it "
            f"is empty. Find out who made the key before going on."
        )
    bind.execute(sa.text("DROP TABLE auth.api_keys"))
    return True


def upgrade() -> None:
    drop_if_empty(op.get_bind())


def downgrade() -> None:
    # Restores the SCHEMA only — the table as migration 077 made it, empty. There
    # is no data to restore: the upgrade refuses to drop a table that holds a row.
    bind = op.get_bind()
    if _table_exists(bind):
        return
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        schema="auth",
    )
