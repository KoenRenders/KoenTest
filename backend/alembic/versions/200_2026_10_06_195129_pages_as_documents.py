"""pages as documents: translations and history, content parsed

CR-17 phase 1 (#1671, Koen's assignment of 6 October 2026). A page's content
becomes a structured document against `cms/schema.py`: one translation row
per (page, language) carrying the draft and the published document, and a
history row per published version.

The data conversion is a measurement, not a hope (F11): each page's stored
HTML is parsed into a document, rendered back, and compared with what the
page shows today. Equal → the document stands in both `draft_json` and
`published_json` (published only where the page was published). Unequal →
the page keeps its HTML (`cms_pages.content`, read-only from now) and is
counted in the log line: it renders exactly as before, through the fallback,
and its words go into `draft_json` as a draft (F11) — publishing is the
author's decision, after comparing the draft with the live page.

`cms_pages.title` stays (a one-release shadow the service keeps in sync with
the translation row); the home-intro and site-footer blocks parse with
`on_page=False`, the rendering they have always had.
"""

import json
import logging
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# The id is a timestamp, not a sequence number (#951). `repr` with double
# quotes (#781): the generated file must already be what `ruff format` writes.
revision = "199_2026_10_06_195129"
down_revision = "199_2026_10_09_034931"
# On the CR-17 branch this migration stood on 197; master added its own
# 198 meanwhile. The branch keeps its migration on ONE linear chain: this
# revision renumbered to 199 and repointed onto master's 198 (the arrangement
# of 8 October 2026 — read the head, never type it).
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def _tenant_languages(bind) -> dict[int, str]:
    settings = bind.execute(
        sa.text(
            "SELECT tenant_id, value FROM kernel_tenant_settings "
            "WHERE key = 'language' AND coalesce(btrim(value), '') <> ''"
        )
    ).fetchall()
    return {tenant_id: value.strip() for tenant_id, value in settings}


def _convert_pages(bind) -> dict:
    """Every page into a translation row; the counts for the log line."""
    from app.domains.cms.parse import parse_html, plain_text_document
    from app.domains.cms.schema import locale_language
    from app.domains.cms.service import SITE_BLOCK_SLUGS

    languages = _tenant_languages(bind)
    pages = bind.execute(
        sa.text("SELECT id, tenant_id, title, slug, content, is_published FROM cms.cms_pages")
    ).fetchall()
    converted, kept_html, published, failed, empty = 0, 0, 0, [], []
    for page_id, tenant_id, title, slug, content, is_published in pages:
        language = locale_language(languages.get(tenant_id, "nl_BE"))
        on_page = slug not in SITE_BLOCK_SLUGS
        existing = bind.execute(
            sa.text(
                "SELECT 1 FROM cms.page_translations WHERE page_id = :page AND language = :lang"
            ),
            {"page": page_id, "lang": language},
        ).first()
        if existing:
            continue
        # One page, one guard (review C2, #1673): a page the converter cannot
        # process counts as "kept her HTML" instead of stopping the deploy —
        # the honest fallback, per page.
        try:
            document = parse_html(content, on_page=on_page)
            draft = document or parse_html(content, on_page=on_page, lenient=True)
        except Exception:
            # The guard (review C2, #1673): one page that makes the converter
            # raise counts as "kept her HTML" instead of stopping the deploy —
            # and her draft holds her WORDS as plain paragraphs (the master
            # CLI's advice): plain text cannot fail, so the net itself is safe.
            log.warning(
                "#1671: page %s (%s) could not be converted; it keeps her HTML", page_id, slug
            )
            draft = plain_text_document(content)
            document = None
        if document is None:
            # F11: a page that does not convert losslessly keeps its live HTML
            # (published_json stays empty, the site renders `content` as
            # today) and gets its words as a DRAFT — publishing it is the
            # author's decision, after comparing with the live page.
            kept_html += 1
            failed.append(f"{page_id} ({slug})")
            bind.execute(
                sa.text(
                    "INSERT INTO cms.page_translations "
                    "(page_id, language, title, menu_label, draft_json, published_json, "
                    " published_at, published_by) "
                    "VALUES (:page, :lang, :title, NULL, CAST(:draft AS jsonb), NULL, NULL, NULL)"
                ),
                {"page": page_id, "lang": language, "title": title, "draft": json.dumps(draft)},
            )
            if not draft.get("content"):
                # Review 4 (Koen, 7 October 2026): a draft that converts to
                # EMPTY stands out in the report instead of being silently
                # filled — words the sanitiser always dropped were never
                # anyone's, and raw content reaches no document (C5).
                empty.append(f"{page_id} ({slug})")
                log.warning(
                    "#1671: page %s (%s) converts to an empty draft; it keeps her HTML",
                    page_id,
                    slug,
                )
            continue
        now = datetime.now(timezone.utc)
        bind.execute(
            sa.text(
                "INSERT INTO cms.page_translations "
                "(page_id, language, title, menu_label, draft_json, published_json, "
                " published_at, published_by) "
                "VALUES (:page, :lang, :title, NULL, CAST(:draft AS jsonb), CAST(:published AS jsonb), "
                " :at, :by)"
            ),
            {
                "page": page_id,
                "lang": language,
                "title": title,
                "draft": json.dumps(document),
                "published": json.dumps(document) if is_published else None,
                "at": now if is_published else None,
                "by": "migration" if is_published else None,
            },
        )
        if is_published:
            # The version the migration publishes carries a history row too
            # (review C2, #1673): the first "Terugzetten" has something to go
            # back to.
            bind.execute(
                sa.text(
                    "INSERT INTO cms.cms_page_history "
                    "(page_id, language, action, document, at, by) "
                    "VALUES (:page, :lang, 'published', CAST(:document AS jsonb), :at, 'migration')"
                ),
                {
                    "page": page_id,
                    "lang": language,
                    "document": json.dumps(document),
                    "at": now,
                },
            )
            published += 1
        converted += 1
        if not document.get("content"):
            # Review 4 (Koen, 7 October 2026): the conversion is lossless —
            # the page rendered empty today too — but the report names her,
            # so an empty editor is a finding and not a surprise.
            empty.append(f"{page_id} ({slug})")
            log.warning("#1671: page %s (%s) converts to an empty document", page_id, slug)
    return {
        "pages": len(pages),
        "converted": converted,
        "kept_html": kept_html,
        "kept": failed,
        "empty": empty,
    }


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names(schema="cms"))

    if "page_translations" not in tables:
        op.create_table(
            "page_translations",
            sa.Column("page_id", sa.Integer(), nullable=False),
            sa.Column("language", sa.String(length=5), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("menu_label", sa.String(length=80), nullable=True),
            sa.Column("draft_json", JSONB(), nullable=True),
            sa.Column("published_json", JSONB(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_by", sa.String(length=255), nullable=True),
            sa.ForeignKeyConstraint(
                ["page_id"], ["cms.cms_pages.id"], ondelete="CASCADE", name="fk_pt_page"
            ),
            sa.ForeignKeyConstraint(
                ["language"], ["mdm.language_codes.code"], name="fk_pt_language"
            ),
            sa.PrimaryKeyConstraint("page_id", "language", name="pk_page_translations"),
            schema="cms",
        )

    if "cms_page_history" not in tables:
        op.create_table(
            "cms_page_history",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("page_id", sa.Integer(), nullable=False),
            sa.Column("language", sa.String(length=5), nullable=False),
            sa.Column("action", sa.String(length=20), nullable=False),
            sa.Column("document", JSONB(), nullable=False),
            sa.Column("at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("by", sa.String(length=255), nullable=True),
            sa.CheckConstraint(
                "action IN ('published', 'restored', 'offline')", name="ck_cph_action"
            ),
            sa.ForeignKeyConstraint(
                ["page_id"], ["cms.cms_pages.id"], ondelete="CASCADE", name="fk_cph_page"
            ),
            sa.PrimaryKeyConstraint("id", name="pk_cms_page_history"),
            schema="cms",
        )
        op.create_index("ix_cms_page_history_page", "cms_page_history", ["page_id"], schema="cms")

    counts = _convert_pages(bind)
    log.info(
        "#1671: %d page(s): %d converted to a document, %d kept their HTML (ids and slugs: %s);"
        " %d convert to an empty draft or document (ids and slugs: %s)",
        counts["pages"],
        counts["converted"],
        counts["kept_html"],
        ", ".join(counts["kept"]) or "none",
        len(counts["empty"]),
        ", ".join(counts["empty"]) or "none",
    )


def downgrade() -> None:
    # Schema only. The documents are a conversion of content that still stands
    # in `cms_pages.content`; a downgrade drops the documents and the history,
    # and the pages fall back to rendering their HTML — which is what they did
    # before this migration, and what the not-lossless ones do anyway.
    op.drop_table("cms_page_history", schema="cms")
    op.drop_table("page_translations", schema="cms")
