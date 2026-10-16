"""The text of a letter is a document of the page editor (CR-17 phase 7b, #2023).

The body of a letter was Trix HTML in `newsletter.newsletters.body_html`, with
three markers in its text (`[[activiteit:…]]`, `[[kalender]]`, `[[afsluiting]]`). It
now is a document of the editor's `letter` set in `body_document`; the mail is built
from it when the letter is sent. Koen, 15 October 2026: if the new editor leaves the
HTML column without a writer, convert EVERYTHING — the sent letters too (two in
PROD, no drafts) — and drop the column in the same change. Measured: every reader of
the stored text (the preview line, the placeholder check, the copy, the archive, the
test mail, the send and Raakje) goes through the one place that renders the
document, or through the marker text derived from it (`letter_markup.py`), so no
reader needs the old column.

The conversion is `markup_to_document`: the lenient one of a page's draft (formatting
may soften, no word is lost) with the three markers become blocks. The archive of
a sent letter shows the letter as it went (Koen, 16 October 2026: "a"): a new column
`sent_body_html` holds the rendered body, written once when the send starts. For the
letters sent before it, this migration fills it with the body rendered at migration
time — the closest to what went out that still exists.

Downgrade restores the text with markers from the documents and drops the column;
the exact Trix markup is not restored.
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
revision = "210_2026_10_15_172727"
down_revision = "210_2026_10_15_215353"
branch_labels = None
depends_on = None


log = logging.getLogger("alembic.runtime.migration")


def _columns(bind) -> set[str]:
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'newsletter' AND table_name = 'newsletters'"
            )
        )
    }


def convert_letters(bind) -> int:
    """The upgrade, on a connection (so a test can run it on a throwaway state):
    add the document column, convert every letter, drop the HTML column.
    Returns how many letters were converted. Idempotent."""
    import json

    from app.domains.newsletter.letter_markup import markup_to_document

    columns = _columns(bind)
    if "body_document" not in columns:
        bind.execute(sa.text("ALTER TABLE newsletter.newsletters ADD COLUMN body_document JSONB"))
    converted = 0
    if "body_html" in columns:
        rows = bind.execute(sa.text("SELECT id, body_html FROM newsletter.newsletters")).fetchall()
        for letter_id, body in rows:
            bind.execute(
                sa.text(
                    "UPDATE newsletter.newsletters SET body_document = CAST(:d AS JSONB) "
                    "WHERE id = :i"
                ),
                {"d": json.dumps(markup_to_document(body)), "i": letter_id},
            )
        converted = len(rows)
        bind.execute(sa.text("ALTER TABLE newsletter.newsletters DROP COLUMN body_html"))
    bind.execute(
        sa.text(
            "UPDATE newsletter.newsletters SET body_document = CAST(:d AS JSONB) "
            "WHERE body_document IS NULL"
        ),
        {"d": json.dumps({"type": "doc", "content": []})},
    )
    bind.execute(
        sa.text("ALTER TABLE newsletter.newsletters ALTER COLUMN body_document SET NOT NULL")
    )
    return converted


def freeze_sent_letters(bind) -> int:
    """Add `sent_body_html` and fill it, for every letter that has started to send and
    has none yet, with the body rendered now. Returns how many were filled. Idempotent."""
    from sqlalchemy.orm import Session

    from app.domains.newsletter.models import Newsletter
    from app.domains.newsletter.service import render_body
    from app.kernel.tenancy import current_tenant_id

    if "sent_body_html" not in _columns(bind):
        bind.execute(sa.text("ALTER TABLE newsletter.newsletters ADD COLUMN sent_body_html TEXT"))
    rows = bind.execute(
        sa.text(
            "SELECT id, tenant_id, body_document, link_base, draft_activity_ids FROM newsletter.newsletters "
            "WHERE status <> 'draft' AND sent_body_html IS NULL ORDER BY id"
        )
    ).fetchall()
    session = Session(bind=bind)
    for letter_id, tenant_id, document, link_base, choices in rows:
        # A bare instance, never a row loaded through the model: the model may know
        # columns a later migration of the same deploy has not added yet.
        letter = Newsletter(
            id=letter_id, body_document=document, link_base=link_base, draft_activity_ids=choices
        )
        token = current_tenant_id.set(tenant_id)
        try:
            body = render_body(session, letter, base_url=link_base or "")
        finally:
            current_tenant_id.reset(token)
        bind.execute(
            sa.text("UPDATE newsletter.newsletters SET sent_body_html = :b WHERE id = :i"),
            {"b": body, "i": letter_id},
        )
    session.close()
    return len(rows)


def upgrade() -> None:
    bind = op.get_bind()
    log.info("#2023: %s letters converted to documents", convert_letters(bind))
    log.info("#2023: %s sent letters frozen as they render now", freeze_sent_letters(bind))


def downgrade() -> None:
    from app.domains.newsletter.letter_markup import document_to_markup

    bind = op.get_bind()
    columns = _columns(bind)
    if "body_html" not in columns:
        bind.execute(
            sa.text(
                "ALTER TABLE newsletter.newsletters ADD COLUMN body_html TEXT NOT NULL DEFAULT ''"
            )
        )
    if "body_document" in columns:
        rows = bind.execute(
            sa.text("SELECT id, body_document FROM newsletter.newsletters")
        ).fetchall()
        for letter_id, document in rows:
            bind.execute(
                sa.text("UPDATE newsletter.newsletters SET body_html = :b WHERE id = :i"),
                {"b": document_to_markup(document), "i": letter_id},
            )
        bind.execute(sa.text("ALTER TABLE newsletter.newsletters DROP COLUMN body_document"))
    if "sent_body_html" in columns:
        bind.execute(sa.text("ALTER TABLE newsletter.newsletters DROP COLUMN sent_body_html"))
