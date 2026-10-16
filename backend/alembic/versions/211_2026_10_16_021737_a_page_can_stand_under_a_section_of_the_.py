"""a page can stand under a section of the menu

CR-17 phase 6 (R8, F10; #2024): the site's menu groups pages under a section,
and a section is itself a page (Koen, 15 October 2026, Q&A nr. 11: "ja"). A page
names the section it stands under; the rules that make it one level deep and
keep the home page out live in the service (`cms.service`), because they read
other rows. The database keeps the two that hold even past a bug: a page is not
its own section, and a section with pages under it cannot be deleted
(`ON DELETE RESTRICT`).

Additive: every page keeps standing in the menu as it does today, under no
section.
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
revision = "211_2026_10_16_021737"
down_revision = "210_2026_10_15_215353"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("cms_pages", schema="cms")}
    if "parent_id" not in columns:
        op.add_column(
            "cms_pages",
            sa.Column(
                "parent_id",
                sa.Integer(),
                sa.ForeignKey("cms.cms_pages.id", ondelete="RESTRICT"),
                nullable=True,
            ),
            schema="cms",
        )
        op.create_index("ix_cms_pages_parent_id", "cms_pages", ["parent_id"], schema="cms")
        op.create_check_constraint(
            "ck_cms_pages_not_own_section", "cms_pages", "parent_id <> id", schema="cms"
        )


def downgrade() -> None:
    # Schema only: which page stood under which section is lost; every page
    # stands in the menu on its own again, as before this migration.
    op.drop_constraint("ck_cms_pages_not_own_section", "cms_pages", schema="cms")
    op.drop_index("ix_cms_pages_parent_id", table_name="cms_pages", schema="cms")
    op.drop_column("cms_pages", "parent_id", schema="cms")
