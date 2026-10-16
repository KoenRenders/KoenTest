"""Count the opens and the clicks of a letter without knowing who (CR-37, #2027).

Two tables in the `newsletter` schema: `letter_links` (the addresses that stood in a
letter, so a click can be sent on to a stored address and never to one the request
names) and `letter_events` (letter, code of one mail, link, day). The event holds no
address, delivery, IP or time of day. Its unique key is `NULLS NOT DISTINCT`: the link is
empty for an open, and a plain unique key would let one code open twice.

It also adds the newsletter section to the privacy page of every tenant that lacks it
(Q5 of the change request, Koen, 15 October 2026: "a"). Plain SQL on the stored documents,
not the CMS's service: a later change to the service must not break a migration that runs
once. For a page that is a document the section goes at the end of the draft (if there is
one) and of the published version, with one new history row, so a *restore* of the latest
version keeps it; a page that kept its HTML gets it in `content`. It runs once per page: a
page that already says it is left alone. Only the Dutch translation, the section being
Dutch text.

Downgrade drops both tables and leaves the section: it is the statement's text, true for
as long as the portal counts.
"""

import json
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
revision = "214_2026_10_16_170934"
down_revision = "213_2026_10_15_205117"
branch_labels = None
depends_on = None


TITLE = "Nieuwsbrief"
TEXT = (
    "Bij de nieuwsbrief tellen we hoeveel brieven geopend worden en hoe vaak een link wordt "
    "aangeklikt. Dat gebeurt anoniem: we houden niet bij wie een brief las, wie op welke link "
    "klikte of wanneer. Een uitgeschreven adres krijgt geen nieuwsbrief meer."
)


def _html_section(level: int) -> str:
    """The section as legacy HTML: `content` is shown one heading level down, a document
    stores the level it shows, so the HTML names the level above the document's."""
    return f"<h{level}>{TITLE}</h{level}><p>{TEXT}</p>"


#: The words by which a page that already says it is recognised.
MARKER = "tellen we hoeveel brieven geopend"


def _level_of(document: dict) -> int:
    """The level the page's own headings use, so the section reads like its neighbours."""
    for node in document.get("content") or []:
        if node.get("type") == "heading":
            return int((node.get("attrs") or {}).get("level") or 3)
    return 3


def _with_section(document: dict) -> dict:
    nodes = list(document.get("content") or [])
    nodes.append(
        {
            "type": "heading",
            "attrs": {"level": _level_of(document)},
            "content": [{"type": "text", "text": TITLE}],
        }
    )
    nodes.append({"type": "paragraph", "content": [{"type": "text", "text": TEXT}]})
    return {**document, "content": nodes}


def add_privacy_section(bind) -> dict[str, int]:
    """Add the section where it is missing; answers what was done, for the log."""
    done = {"documents": 0, "html": 0, "left alone": 0}
    pages = bind.execute(
        sa.text("SELECT id, content FROM cms.cms_pages WHERE slug = 'privacy'")
    ).all()
    for page_id, content in pages:
        translations = bind.execute(
            sa.text(
                "SELECT draft_json, published_json FROM cms.page_translations "
                "WHERE page_id = :p AND language = 'nl'"
            ),
            {"p": page_id},
        ).first()
        if translations is not None:
            draft, published = translations
            if MARKER in json.dumps([draft, published], ensure_ascii=False):
                done["left alone"] += 1
                continue
            new_draft = _with_section(draft) if draft else None
            new_published = _with_section(published) if published else None
            bind.execute(
                sa.text(
                    "UPDATE cms.page_translations SET draft_json = CAST(:d AS json), "
                    "published_json = CAST(:p AS json) WHERE page_id = :page AND language = 'nl'"
                ),
                {
                    "d": json.dumps(new_draft) if new_draft else None,
                    "p": json.dumps(new_published) if new_published else None,
                    "page": page_id,
                },
            )
            if new_published:
                bind.execute(
                    sa.text(
                        "INSERT INTO cms.cms_page_history (page_id, language, action, document, at, by) "
                        "VALUES (:page, 'nl', 'published', CAST(:doc AS json), now(), 'migration')"
                    ),
                    {"page": page_id, "doc": json.dumps(new_published)},
                )
            if content is not None and MARKER not in content:
                # The page still holds the HTML it had before it became a document, and
                # a gate compares the two renderings: both say the same.
                bind.execute(
                    sa.text("UPDATE cms.cms_pages SET content = :c WHERE id = :p"),
                    {
                        "c": content + _html_section(max(1, _level_of(published or draft) - 1)),
                        "p": page_id,
                    },
                )
            done["documents"] += 1
        elif content is not None and MARKER not in content:
            bind.execute(
                sa.text("UPDATE cms.cms_pages SET content = :c WHERE id = :p"),
                {"c": content + _html_section(3), "p": page_id},
            )
            done["html"] += 1
        else:
            done["left alone"] += 1
    return done


def upgrade() -> None:
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names(schema="newsletter")
    if "letter_links" not in tables:
        op.create_table(
            "letter_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column(
                "newsletter_id",
                sa.Integer(),
                sa.ForeignKey("newsletter.newsletters.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("url", sa.Text(), nullable=False),
            sa.UniqueConstraint("newsletter_id", "url", name="uq_letter_link_url"),
            schema="newsletter",
        )
        op.create_index(
            "ix_newsletter_letter_links_tenant_id",
            "letter_links",
            ["tenant_id"],
            schema="newsletter",
        )
        op.create_index(
            "ix_newsletter_letter_links_newsletter_id",
            "letter_links",
            ["newsletter_id"],
            schema="newsletter",
        )
    if "letter_events" not in tables:
        op.create_table(
            "letter_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column(
                "newsletter_id",
                sa.Integer(),
                sa.ForeignKey("newsletter.newsletters.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("code", sa.String(80), nullable=False),
            sa.Column(
                "link_id",
                sa.Integer(),
                sa.ForeignKey("newsletter.letter_links.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("day", sa.Date(), nullable=False),
            sa.UniqueConstraint(
                "newsletter_id",
                "code",
                "link_id",
                name="uq_letter_event",
                postgresql_nulls_not_distinct=True,
            ),
            schema="newsletter",
        )
        op.create_index(
            "ix_newsletter_letter_events_tenant_id",
            "letter_events",
            ["tenant_id"],
            schema="newsletter",
        )
        op.create_index(
            "ix_newsletter_letter_events_newsletter_id",
            "letter_events",
            ["newsletter_id"],
            schema="newsletter",
        )
    done = add_privacy_section(bind)
    logging.getLogger("alembic.runtime.migration").info("#2027: privacy page section %s", done)


def downgrade() -> None:
    op.drop_table("letter_events", schema="newsletter")
    op.drop_table("letter_links", schema="newsletter")
