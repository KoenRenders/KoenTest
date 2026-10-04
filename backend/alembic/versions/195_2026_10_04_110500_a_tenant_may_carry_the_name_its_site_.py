"""a tenant may carry the name its site shows

#1546 (CR-19). A site named itself by its tenant's organisation name. A tenant
may now carry a name of its own for its site — the wordmark, the browser tab, the
footer's "©", the list of sites (#1543) and the mail sender's name — beside the
legal name of the organisation behind it, which stays where it is. Empty, the site
shows the name of the organisation behind it (#1550): its own by default.

`#945` foresaw it: a brand name that differs from the legal name is a column on
the organisation, not a tenant setting. NULL keeps every site as it was.
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
revision = "195_2026_10_04_110500"
down_revision = "194_2026_10_04_104417"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns("organizations", schema="mdm")
    }
    if "site_name" not in columns:
        op.add_column(
            "organizations", sa.Column("site_name", sa.String(255), nullable=True), schema="mdm"
        )


def downgrade() -> None:
    # The names typed in are lost; every site falls back to its organisation's name.
    op.drop_column("organizations", "site_name", schema="mdm")
