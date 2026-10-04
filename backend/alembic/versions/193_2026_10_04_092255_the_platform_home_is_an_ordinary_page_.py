"""the platform home is an ordinary page with the sites placeholder

#1543 (CR-19). The platform's home was a fixed template (#1525) with its text in
the platform's `home-intro` block (migration 192) and a list of accounts and
tenants built in code. It becomes an ordinary CMS page, flagged as the home page
(`is_home`, #1477), which the operator builds under Pagina's like any site's.

The page starts with what the platform showed: the block's text, followed by
`{{tenants}}`, the placeholder that renders the list of accounts and their
sites where the template put it. Its title is the platform organisation's name,
not a literal, so it follows the name the site carries. The block is removed
once its text has moved, so the text exists once.

Nothing happens when the platform already has a home page, or has no row.
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
revision = "193_2026_10_04_092255"
down_revision = "192_2026_10_04_055352"
branch_labels = None
depends_on = None

SLUG = "start"
LIST = "<p>{{tenants}}</p>"


def upgrade() -> None:
    bind = op.get_bind()
    made = bind.execute(
        sa.text(
            """
            INSERT INTO cms.cms_pages
                (tenant_id, title, slug, content, is_published, show_in_nav,
                 is_home, sort_order, created_at, updated_at)
            SELECT o.id, o.name, :slug, COALESCE(intro.content, '') || :list,
                   true, false, true, 0, now(), now()
            FROM mdm.organizations o
            LEFT JOIN cms.cms_pages intro
                   ON intro.tenant_id = o.id AND intro.slug = 'home-intro'
            WHERE o.org_type = 'PLATFORM'
              AND NOT EXISTS (
                  SELECT 1 FROM cms.cms_pages p WHERE p.tenant_id = o.id AND p.is_home)
            ON CONFLICT (tenant_id, slug) DO NOTHING
            RETURNING tenant_id
            """
        ),
        {"slug": SLUG, "list": LIST},
    ).fetchall()
    for (tenant_id,) in made:
        bind.execute(
            sa.text("DELETE FROM cms.cms_pages WHERE tenant_id = :t AND slug = 'home-intro'"),
            {"t": tenant_id},
        )


def downgrade() -> None:
    # The page goes back to being the block it came from: its content without the
    # list, which the old landing rendered itself. An operator's edits to the page
    # travel back with it — they are the platform's text either way.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO cms.cms_pages
                (tenant_id, title, slug, content, is_published, show_in_nav,
                 is_home, sort_order, created_at, updated_at)
            SELECT p.tenant_id, 'Home intro', 'home-intro', replace(p.content, :list, ''),
                   true, false, false, 0, now(), now()
            FROM cms.cms_pages p
            JOIN mdm.organizations o ON o.id = p.tenant_id AND o.org_type = 'PLATFORM'
            WHERE p.slug = :slug AND p.is_home
            ON CONFLICT (tenant_id, slug) DO NOTHING
            """
        ),
        {"slug": SLUG, "list": LIST},
    )
    bind.execute(
        sa.text(
            """
            DELETE FROM cms.cms_pages p USING mdm.organizations o
            WHERE o.id = p.tenant_id AND o.org_type = 'PLATFORM' AND p.slug = :slug AND p.is_home
            """
        ),
        {"slug": SLUG},
    )
