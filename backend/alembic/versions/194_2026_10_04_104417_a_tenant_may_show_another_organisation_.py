"""a tenant may show another organisation of its account

#1550 (CR-19). A site shows whose it is — name, legal form, numbers, address,
contact and bank account — and until now that was always the tenant's own
organisation row. A tenant may now point at another organisation within its own
account (the account itself, or another organisation of that account), so a
brand's site or the platform shows the data of the company behind it without
copying it. NULL means the tenant's own row, so nothing changes for a tenant
without a choice.

The downgrade drops the column: the choice is lost, the data it pointed at is
not (it was never copied).
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
revision = "194_2026_10_04_104417"
down_revision = "193_2026_10_04_092255"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("organizations", schema="mdm")
    }
    if "site_organization_id" not in columns:
        op.add_column(
            "organizations",
            sa.Column(
                "site_organization_id",
                sa.Integer(),
                sa.ForeignKey("mdm.organizations.id", name="fk_organizations_site_organization"),
                nullable=True,
            ),
            schema="mdm",
        )


def downgrade() -> None:
    op.drop_column("organizations", "site_organization_id", schema="mdm")
