"""a page can open with a hero (CR-32 F4, B8.11)

The hero is a property of the page, not a block of the document: `opening`
says how the page opens — the title line (today) or a hero — and `hero` holds
its tone, eyebrow, lead and up to two buttons, validated at the save by
`cms.schema.validate_hero`. Additive: every page keeps `title_line` and no
hero.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "205_2026_10_15_082601"
down_revision = "204_2026_10_15_080810"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("cms_pages", schema="cms")}
    if "opening" not in columns:
        op.add_column(
            "cms_pages",
            sa.Column("opening", sa.String(length=16), nullable=False, server_default="title_line"),
            schema="cms",
        )
        op.create_check_constraint(
            "ck_cms_pages_opening",
            "cms_pages",
            "opening IN ('title_line', 'hero')",
            schema="cms",
        )
    if "hero" not in columns:
        op.add_column("cms_pages", sa.Column("hero", JSONB(), nullable=True), schema="cms")


def downgrade() -> None:
    op.drop_column("cms_pages", "hero", schema="cms")
    op.drop_constraint("ck_cms_pages_opening", "cms_pages", schema="cms")
    op.drop_column("cms_pages", "opening", schema="cms")
