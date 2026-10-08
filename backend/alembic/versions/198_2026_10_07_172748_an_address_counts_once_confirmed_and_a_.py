"""an address counts once confirmed and a code says what it is for

CR-22 (#1700), slice S1 (#1704): the one migration of the change. Everyone
who signs in gets an account — a person in master data — and signing in sends a
code to an e-mail address. That only works when the address says who signs in,
so two things have to be true in the data before any of the screens exist:

- **An address counts only once its owner has proven he reads it**
  (`mdm.contact_details.confirmed_at`). Until now an address typed in Mijn
  gezin signed in at once, unchecked. Every existing row is marked as
  confirmed at its creation: the addresses people sign in with today keep
  working, and the rule starts with the next address that is typed.
- **A code says what it is for** (`auth.login_tokens.purpose`, with the code
  list `auth.login_purpose_codes`, and `payload` for what the purpose needs).
  Signing in, making an account and confirming an address share the one
  hardened mechanism (#268, #395) instead of growing a second token table.

Additive: a new nullable column, a new column with a default, a new list.
Nothing reads them yet — the slices after this one do.

Measured before writing (`AGENTS.md`, *Alembic migrations*): no CHECK
constraint on `auth.login_tokens`; one on `mdm.contact_details`
(`ck_contact_details_person_xor_organization`), which says a row belongs to a
person or to an organisation and is not touched by a timestamp.
"""

import logging

import sqlalchemy as sa
from alembic import op

from app.domains.auth.codes import LOGIN_PURPOSE_CODES
from app.kernel.codes import create_code_list

logger = logging.getLogger("alembic.runtime.migration")

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
revision = "198_2026_10_07_172748"
down_revision = "197_2026_10_05_075704"
branch_labels = None
depends_on = None


def _columns(schema: str, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table, schema=schema)}


def upgrade() -> None:
    bind = op.get_bind()

    if "confirmed_at" not in _columns("mdm", "contact_details"):
        op.add_column(
            "contact_details",
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            schema="mdm",
        )
    # Every row that exists today counts, as of the day it was made — also a
    # soft-deleted one and an organisation's: the column says since when a
    # detail counts, and none of these was ever waiting for a code.
    backfilled = bind.execute(
        sa.text(
            "UPDATE mdm.contact_details SET confirmed_at = created_at WHERE confirmed_at IS NULL"
        )
    ).rowcount
    logger.info("#1704: %d contact detail(s) marked as confirmed at their creation", backfilled)

    token_columns = _columns("auth", "login_tokens")
    if "purpose" not in token_columns:
        op.add_column(
            "login_tokens",
            sa.Column("purpose", sa.String(20), nullable=False, server_default="SIGN_IN"),
            schema="auth",
        )
    if "payload" not in token_columns:
        op.add_column("login_tokens", sa.Column("payload", sa.JSON(), nullable=True), schema="auth")
    create_code_list(
        op,
        schema="auth",
        name="login_purpose",
        codes=LOGIN_PURPOSE_CODES,
        fk_from=("auth.login_tokens.purpose",),
        code_length=20,
    )


def downgrade() -> None:
    # Does this downgrade restore the DATA too, or only the schema? Say so out
    # loud. A partial reversal that passes itself off as a whole one is worse
    # than one that is honest about what it does not do.
    #
    # Schema only, and it loses data: which addresses were still waiting for
    # their code is gone with the column, so back on the old code every address
    # signs in again at once — which is what the old code does. A token's
    # purpose and payload go too: a code for a new account or a new address
    # that was still open becomes a plain sign-in code for that address.
    op.drop_constraint(
        "fk_login_tokens_purpose_code", "login_tokens", schema="auth", type_="foreignkey"
    )
    op.drop_table("login_purpose_labels", schema="auth")
    op.drop_table("login_purpose_codes", schema="auth")
    op.drop_column("login_tokens", "payload", schema="auth")
    op.drop_column("login_tokens", "purpose", schema="auth")
    op.drop_column("contact_details", "confirmed_at", schema="mdm")
