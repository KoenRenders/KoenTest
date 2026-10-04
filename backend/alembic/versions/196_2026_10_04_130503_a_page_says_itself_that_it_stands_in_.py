"""a page says itself that it stands in the footer

#1569 (Koen, 4 October 2026). Where a page appears is set on the page itself:
home and the header menu already were checkboxes on the page, the footer was a
tenant setting — `privacy_url`, a typed path. One mechanism instead of two: a
page carries `show_in_footer`, and the setting goes.

So that no footer changes at the deploy, the page each tenant's setting points
to (`'/' + slug`, published) gets the flag. A value that matches no published
page is counted and logged, not guessed: an address outside the site, or a path
to a page that does not exist, has no page to tick. The rows of the setting are
removed after that, matched or not — the setting no longer exists.
"""

import logging

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
revision = "196_2026_10_04_130503"
down_revision = "195_2026_10_04_110500"
branch_labels = None
depends_on = None


log = logging.getLogger("alembic.runtime.migration")

SETTING = "privacy_url"


def move_settings_to_pages(bind) -> dict:
    """Tick the page each tenant's setting points to, then remove the setting.

    Returns the counts the log line reports: settings with a value, moved,
    the tenant ids whose value matched no published page, rows removed.
    """
    settings = bind.execute(
        sa.text(
            "SELECT tenant_id, value FROM kernel_tenant_settings "
            "WHERE key = :key AND coalesce(btrim(value), '') <> ''"
        ),
        {"key": SETTING},
    ).fetchall()
    moved, unmatched = 0, []
    for tenant_id, value in settings:
        path = value.strip().rstrip("/")
        ticked = 0
        if path.startswith("/") and "/" not in path[1:]:
            ticked = bind.execute(
                sa.text(
                    "UPDATE cms.cms_pages SET show_in_footer = true "
                    "WHERE tenant_id = :tenant AND slug = :slug AND is_published"
                ),
                {"tenant": tenant_id, "slug": path[1:]},
            ).rowcount
        if ticked:
            moved += 1
        else:
            unmatched.append(tenant_id)
    removed = bind.execute(
        sa.text("DELETE FROM kernel_tenant_settings WHERE key = :key"), {"key": SETTING}
    ).rowcount
    return {"with_value": len(settings), "moved": moved, "unmatched": unmatched, "removed": removed}


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("cms_pages", schema="cms")}
    if "show_in_footer" not in columns:
        op.add_column(
            "cms_pages",
            sa.Column("show_in_footer", sa.Boolean(), nullable=False, server_default=sa.false()),
            schema="cms",
        )

    counts = move_settings_to_pages(bind)
    log.info(
        "#1569: %d privacy_url setting(s) with a value: %d moved to a footer page, "
        "%d matched no published page (tenant ids: %s); %d setting row(s) removed",
        counts["with_value"],
        counts["moved"],
        len(counts["unmatched"]),
        ", ".join(str(t) for t in counts["unmatched"]) or "none",
        counts["removed"],
    )


def downgrade() -> None:
    # Does this downgrade restore the DATA too, or only the schema? Say so out
    # loud. A partial reversal that passes itself off as a whole one is worse
    # than one that is honest about what it does not do.
    #
    # Partly. Each tenant gets the setting back for its FIRST footer page (by
    # sort order), as `'/' + slug`; a second footer page has no place in one
    # setting and loses its place in the footer, and a value that matched no
    # page at the upgrade is not restored — it was removed, not kept.
    op.execute(
        sa.text(
            "INSERT INTO kernel_tenant_settings (tenant_id, key, value, updated_at) "
            "SELECT DISTINCT ON (tenant_id) tenant_id, 'privacy_url', '/' || slug, now() "
            "FROM cms.cms_pages WHERE show_in_footer AND is_published "
            "ORDER BY tenant_id, sort_order, title "
            "ON CONFLICT ON CONSTRAINT uq_tenant_setting DO NOTHING"
        )
    )
    op.drop_column("cms_pages", "show_in_footer", schema="cms")
