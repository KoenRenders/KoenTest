"""tenant kind: what a tenant's site is for

CR-19 (#1468), phase 2 (#1478). A tenant is a VERENIGING or a BEDRIJF; the kind
gives a new tenant its module set and, later, the template to reset to. It is a
code list per CR-12 (`mdm.tenant_kind_codes` with its labels) and a column on
the organisation, next to `legal_form` — law and purpose are two questions.

Every existing UNIT becomes VERENIGING: each tenant today is an association.
ACCOUNT and PLATFORM rows stay NULL; they are no tenant site of their own kind.
"""

import sqlalchemy as sa
from alembic import op

from app.domains.mdm.codes import TENANT_KIND_CODES
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
revision = "188_2026_10_02_135515"
down_revision = "187_2026_10_02_123250"
branch_labels = None
depends_on = None


def _has_kind() -> bool:
    columns = sa.inspect(op.get_bind()).get_columns("organizations", schema="mdm")
    return "kind" in {c["name"] for c in columns}


def upgrade() -> None:
    if not _has_kind():
        op.add_column(
            "organizations", sa.Column("kind", sa.String(20), nullable=True), schema="mdm"
        )
    op.execute(
        "UPDATE mdm.organizations SET kind = 'VERENIGING' WHERE org_type = 'UNIT' AND kind IS NULL"
    )
    create_code_list(
        op,
        schema="mdm",
        name="tenant_kind",
        codes=TENANT_KIND_CODES,
        fk_from=("mdm.organizations.kind",),
        code_length=20,
    )


def downgrade() -> None:
    # Schema and data: the kinds go. Back on the old code every tenant is an
    # association again, which is what the old code assumes.
    op.drop_constraint(
        "fk_organizations_kind_code", "organizations", schema="mdm", type_="foreignkey"
    )
    op.drop_table("tenant_kind_labels", schema="mdm")
    op.drop_table("tenant_kind_codes", schema="mdm")
    op.drop_column("organizations", "kind", schema="mdm")
