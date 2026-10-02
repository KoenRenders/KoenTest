"""cms page can be the home page

CR-19 (#1468), phase 2 (#1477). A company's home page is a page of its own,
not the association's composition of a membership band and activity cards. A
tenant may flag one page as its home; `/` then renders that page, and falls
back to the shell's composition when none is flagged. At most one per tenant:
a partial unique index, not a rule the code alone keeps.
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
revision = "189_2026_10_02_142946"
down_revision = "188_2026_10_02_135515"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("cms_pages", schema="cms")}
    if "is_home" not in columns:
        op.add_column(
            "cms_pages",
            sa.Column("is_home", sa.Boolean(), nullable=False, server_default=sa.false()),
            schema="cms",
        )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_cms_pages_one_home_per_tenant "
        "ON cms.cms_pages (tenant_id) WHERE is_home"
    )


def downgrade() -> None:
    # Schema and data: the flag goes, and `/` is the composition again.
    op.execute("DROP INDEX IF EXISTS cms.ux_cms_pages_one_home_per_tenant")
    op.drop_column("cms_pages", "is_home", schema="cms")
