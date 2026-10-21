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
may soften, no word is lost) with the three markers become blocks. Measured on PROD and UAT on 16 October 2026: no picture in any
stored letter (0 `<img` and 0 `<figure`), so the conversion has no figure to map.

The archive of a sent letter shows the letter as it went (Koen, 16 October 2026: "a"): a new column
`sent_body_html` holds the rendered body, written once when the send starts. This
migration adds the column; the letters sent before it are filled, and the CHECK that makes
the column required for a sent letter is set, in migration 320 (#2195).

This migration does not read the models of today: both migrations of a deploy run with the
models of the deploy's last revision, so a model that knows a column or a table a later
migration adds would fail here, halfway through the upgrade. It imports the pure
`markup_to_document` only.

Downgrade restores the text with markers from the documents and drops the column;
the exact Trix markup is not restored.

Amended twice after v2.17.0 (#2195), the named exception to "a merged migration is never
modified": this migration never completed on PROD (its transaction rolled back whole to
202), and HDEV and UAT are past it. It used to freeze the sent letters here, rendering them
with the app's code as it stands at the head, on the schema of this revision: the render
asks the clock for a day (no tenant in a migration), and with a tenant set it reads
`mdm.tenants`, which only exists from 313. The freeze moved to migration 320, at the head
of the chain. Koen, 21 October 2026, to "Mag migratie 212 aangepast worden, omdat ze op
PROD nooit is afgelopen?": "ja, 212 mag aangepast worden"; and to "Mag dev1 dit zo bouwen:
212 een tweede keer aanpassen en een nieuwe migratie na 319 toevoegen?": "ja".
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
revision = "212_2026_10_15_172727"
down_revision = "211_2026_10_16_021737"
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


def add_frozen_column(bind) -> None:
    """The column the archive reads: `sent_body_html`, nullable here. The letters that
    went before it get their body, and the CHECK that makes it required for a sent letter,
    in migration 320."""
    if "sent_body_html" not in _columns(bind):
        bind.execute(sa.text("ALTER TABLE newsletter.newsletters ADD COLUMN sent_body_html TEXT"))


def upgrade() -> None:
    bind = op.get_bind()
    log.info("#2023: %s letters converted to documents", convert_letters(bind))
    add_frozen_column(bind)


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
