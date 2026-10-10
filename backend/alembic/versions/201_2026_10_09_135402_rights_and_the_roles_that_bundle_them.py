"""rights and the roles that bundle them

CR-24 (#1722), the one migration of the change. Every gate of the back office
asks for a role by name today, so a new kind of work means editing the gates
by hand. From this change on a gate asks for a **right**, and a role is a
**bundle** of rights kept as rows — so the next role is rows, not code.

This migration brings what that needs to exist before any gate changes:

- the rights themselves, as a code list (`auth.right_codes`, `right_labels`);
- the bundles (`auth.role_rights`): for ADMIN, FINANCE and OPERATOR exactly
  what each role opens today, so nobody's reach changes on the day the gates
  switch over (R7) — with one deliberate widening, the workbench for FINANCE
  (Q11);
- four roles: MASTERDATA, and PRICING, SALES and STOCK for the webshop (CR-21);
- the label of FINANCE, which reads Boekhouding from now on (Q8). The code
  stays.

**The bundles are written out here and not read from the application.** A
constant this file imported would let a later edit reach a fresh database and
no existing one, without anything turning red. Here they are history; the rule
is `auth/tests/test_rights_core.py`, which holds the rows against the table of
CR-24 §B1. A bundle changes by a new migration.

Per kind of object two rights (D1): a role that holds the changing right holds
the viewing right too. ADMIN holds nothing of the webshop, viewing included
(Q10); ACCOUNT_ADMIN holds nothing at all (R11).

Additive and idempotent: tables made when absent, rows inserted when absent.
Nothing asks a right yet.

Measured before writing (`AGENTS.md`, *Alembic migrations*): no CHECK
constraint on `auth.role_codes`, `auth.user_roles` or
`workflow.workflow_tasks`, the three tables that hold a role code;
`auth.role_codes.code` is 20 wide and the longest new code is 10.
"""

import sqlalchemy as sa
from alembic import op

from app.domains.auth.codes import RIGHT_CODES, ROLE_CODES
from app.kernel.codes import create_code_list

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
revision = "201_2026_10_09_135402"
down_revision = "200_2026_10_09_060229"
branch_labels = None
depends_on = None

NEW_ROLES = ("MASTERDATA", "PRICING", "SALES", "STOCK")

#: The objects whose changing right is `<object>.manage`; master data's is
#: `<object>.masterdata`.
_BOARD = ("activity", "form", "page", "media", "design", "newsletter", "meeting", "report")
_BOARD += ("user", "settings")


def _both(obj: str, change: str = "manage") -> tuple[str, str]:
    return (f"{obj}.view", f"{obj}.{change}")


#: CR-24 §B1, the table of rights per role, with the viewing right beside every
#: changing one. OPERATOR holds every right there is.
BUNDLES: dict[str, tuple[str, ...]] = {
    "ADMIN": (
        *(code for obj in _BOARD for code in _both(obj)),
        *_both("party", "masterdata"),
        "assistant.use",
        "payment.view",
        "workbench.use",
    ),
    "FINANCE": (*_both("payment"), "workbench.use"),
    "MASTERDATA": (
        *_both("party", "masterdata"),
        *_both("product", "masterdata"),
        "workbench.use",
    ),
    "PRICING": (*_both("price"), "workbench.use"),
    "SALES": (*_both("sales"), "workbench.use"),
    "STOCK": (*_both("stock"), "workbench.use"),
}


def upgrade() -> None:
    bind = op.get_bind()

    # The four roles and their labels: the role list exists, so the helper
    # only adds what is absent.
    new_roles = [seed for seed in ROLE_CODES if seed.code in NEW_ROLES]
    assert len(new_roles) == len(NEW_ROLES), "a new role has no seed in auth/codes.py"
    create_code_list(op, schema="auth", name="role", codes=new_roles, code_length=20)

    finance = next(seed for seed in ROLE_CODES if seed.code == "FINANCE")
    for language in ("nl", "en"):
        bind.execute(
            sa.text(
                "UPDATE auth.role_labels SET value = :value, updated_at = now() "
                "WHERE code = 'FINANCE' AND language = :language AND value <> :value"
            ),
            {"value": finance.label(language), "language": language},
        )

    create_code_list(op, schema="auth", name="right", codes=RIGHT_CODES)

    if not sa.inspect(bind).has_table("role_rights", schema="auth"):
        op.create_table(
            "role_rights",
            sa.Column("role_code", sa.String(20), primary_key=True),
            sa.Column("right_code", sa.String(50), primary_key=True),
            sa.ForeignKeyConstraint(
                ["role_code"], ["auth.role_codes.code"], name="fk_role_rights_role_code_code"
            ),
            sa.ForeignKeyConstraint(
                ["right_code"], ["auth.right_codes.code"], name="fk_role_rights_right_code_code"
            ),
            schema="auth",
        )

    bundles = dict(BUNDLES, OPERATOR=tuple(seed.code for seed in RIGHT_CODES))
    for role, rights in bundles.items():
        for right in rights:
            bind.execute(
                sa.text(
                    "INSERT INTO auth.role_rights (role_code, right_code) "
                    "VALUES (:role, :right) ON CONFLICT DO NOTHING"
                ),
                {"role": role, "right": right},
            )


def downgrade() -> None:
    # Does this downgrade restore the DATA too, or only the schema? Say so out
    # loud. A partial reversal that passes itself off as a whole one is worse
    # than one that is honest about what it does not do.
    #
    # It restores both, on one condition: nobody holds one of the four new
    # roles. A user who does keeps the role code from being deleted (the
    # foreign key of `auth.user_roles` refuses), and the downgrade stops there
    # rather than take a role away from someone: withdraw those roles first.
    bind = op.get_bind()
    op.drop_table("role_rights", schema="auth")
    op.drop_table("right_labels", schema="auth")
    op.drop_table("right_codes", schema="auth")
    for language, value in (("nl", "Penningmeester"), ("en", "Treasurer")):
        bind.execute(
            sa.text(
                "UPDATE auth.role_labels SET value = :value "
                "WHERE code = 'FINANCE' AND language = :language"
            ),
            {"value": value, "language": language},
        )
    for table in ("role_labels", "role_codes"):
        bind.execute(
            sa.text(f"DELETE FROM auth.{table} WHERE code = ANY(:codes)"),
            {"codes": list(NEW_ROLES)},
        )
