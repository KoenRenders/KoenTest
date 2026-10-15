"""every tenant gets its home page as a page of the CMS (CR-32 R17, phase 5)

The home page used to be a template (`home.html`) composed from the `home-intro`
block, the membership band and the activity list. It is a page of the CMS now,
flagged as the tenant's home (CR-19), made of the same pieces: the intro, the
band (a section in the accent tone with the fee and the year as values and the
two buttons) and the activities block. Koen, 15 October 2026 ("a op 4 en 5"):
a seed makes it for a tenant without a flagged home page and never touches an
existing page; the text of `home-intro` moves into it, and `home-intro` leaves
the site blocks — its row stays, not published.

This is that seed for the tenants that exist. A tenant created later gets the
page from `cms.service.seed_site_blocks`; both build the document with the one
pure `cms.home_page.home_document`. Idempotent: a tenant with a flagged page
(this migration's or its own) is skipped, and the page is made once.
"""

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "208_2026_10_15_132019"
down_revision = "207_2026_10_15_122413"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    made, skipped = make_home_pages(op.get_bind())
    log.info(
        "CR-32 R17: %s tenants got a home page (%s); %s kept the one they had or could not take a slug",
        len(made),
        ", ".join(str(t) for t in made) or "none",
        len(skipped),
    )


def make_home_pages(bind) -> tuple[list[int], list[int]]:
    """The home page of every tenant that has none, by plain SQL on `bind` (an ORM
    call would break the day `cms_pages` gains a column this migration runs
    before). The document is the one the seed of a new tenant builds
    (`cms.home_page.home_document`); a test holds the two equal. Returns the
    tenants it made a page for and the ones it left alone."""
    from app.domains.cms.home_page import home_document

    tenants = [
        row[0]
        for row in bind.execute(sa.text("SELECT DISTINCT tenant_id FROM cms.cms_pages")).fetchall()
    ]
    made, skipped = [], []
    for tenant_id in tenants:
        if bind.execute(
            sa.text("SELECT 1 FROM cms.cms_pages WHERE tenant_id = :t AND is_home"),
            {"t": tenant_id},
        ).first():
            skipped.append(tenant_id)
            continue
        taken = {
            row[0]
            for row in bind.execute(
                sa.text("SELECT slug FROM cms.cms_pages WHERE tenant_id = :t"), {"t": tenant_id}
            ).fetchall()
        }
        slug = "start" if "start" not in taken else "startpagina"
        if slug in taken:
            skipped.append(tenant_id)
            continue
        name = (
            bind.execute(
                sa.text("SELECT name FROM mdm.organizations WHERE id = :t"), {"t": tenant_id}
            ).scalar()
            or "Startpagina"
        )
        modules = {
            row[0]
            for row in bind.execute(
                sa.text("SELECT module_code FROM mdm.tenant_modules WHERE tenant_id = :t"),
                {"t": tenant_id},
            ).fetchall()
        }
        intro = bind.execute(
            sa.text(
                "SELECT p.id, t.language, coalesce(t.published_json, t.draft_json) "
                "FROM cms.cms_pages p LEFT JOIN cms.page_translations t ON t.page_id = p.id "
                "WHERE p.tenant_id = :t AND p.slug = 'home-intro' ORDER BY t.language LIMIT 1"
            ),
            {"t": tenant_id},
        ).first()
        language = (intro[1] if intro and intro[1] else None) or "nl"
        intro_blocks = list((intro[2] or {}).get("content") or []) if intro else []
        document = home_document(
            intro_blocks,
            membership="membership" in modules,
            activities="activities" in modules,
            contact_slug="berichten" if "forms" in modules else None,
        )
        title = name[:200]
        page_id = bind.execute(
            sa.text(
                "INSERT INTO cms.cms_pages (tenant_id, title, slug, is_published, show_in_nav, "
                "is_home, show_in_footer, sort_order, opening, created_at, updated_at) "
                "VALUES (:t, :title, :slug, true, false, true, false, 0, 'title_line', now(), now()) "
                "RETURNING id"
            ),
            {"t": tenant_id, "title": title, "slug": slug},
        ).scalar()
        bind.execute(
            sa.text(
                "INSERT INTO cms.page_translations (page_id, language, title, draft_json, "
                "published_json, published_at, published_by) "
                "VALUES (:p, :lang, :title, :doc, :doc, now(), 'migration 208')"
            ).bindparams(sa.bindparam("doc", type_=JSONB)),
            {"p": page_id, "lang": language, "title": title, "doc": document},
        )
        bind.execute(
            sa.text(
                "INSERT INTO cms.cms_page_history (page_id, language, action, document, at, by) "
                "VALUES (:p, :lang, 'published', :doc, now(), 'migration 208')"
            ).bindparams(sa.bindparam("doc", type_=JSONB)),
            {"p": page_id, "lang": language, "doc": document},
        )
        # The intro's text lives in the page now; the block is not a site block any
        # more and must not be served at an address of its own.
        bind.execute(
            sa.text(
                "UPDATE cms.cms_pages SET is_published = false "
                "WHERE tenant_id = :t AND slug = 'home-intro'"
            ),
            {"t": tenant_id},
        )
        made.append(tenant_id)
    return made, skipped


def downgrade() -> None:
    # The pages this made are told apart by their author; the intro goes live again.
    bind = op.get_bind()
    ids = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT page_id FROM cms.page_translations WHERE published_by = 'migration 208'"
            )
        ).fetchall()
    ]
    if ids:
        bind.execute(sa.text("DELETE FROM cms.cms_pages WHERE id = ANY(:ids)"), {"ids": ids})
    bind.execute(sa.text("UPDATE cms.cms_pages SET is_published = true WHERE slug = 'home-intro'"))
