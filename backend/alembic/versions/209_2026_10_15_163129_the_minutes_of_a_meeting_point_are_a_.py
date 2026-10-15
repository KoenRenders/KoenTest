"""The minutes of a meeting point are a document of the page editor (CR-17 phase 7, #2023).

The notes of a point were Trix HTML in `meetings.meeting_items.notes`; they now
are a document of the editor's `notes` set in `notes_document`, rendered for the
screen and the PDF at read time. Koen, 15 October 2026: if the new editor leaves
the HTML column without a writer, convert EVERYTHING and drop the old column in
the same change. Measured before building: the readers of the stored HTML (the
screen, the PDF, the newsletter drafting's plain text, the carry-over and the
copy of a point) all go through the one function that renders the document, so
no reader needs the old column and the answer is "convert and drop".

The conversion is the lenient one of a page's draft (`document_from_trix`):
formatting may soften, no word is lost. A point that is blank stays empty. The
point of a meeting already sent keeps what it says: the archived PDF was frozen
when it went, and the screen shows the converted words.

Downgrade restores the HTML from the documents (rendered the way the screen
renders them) and drops the column; the exact Trix markup is not restored.
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
revision = "209_2026_10_15_163129"
down_revision = "208_2026_10_15_132019"
branch_labels = None
depends_on = None


log = logging.getLogger("alembic.runtime.migration")


def _columns(bind) -> set[str]:
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'meetings' AND table_name = 'meeting_items'"
            )
        )
    }


def convert_notes(bind) -> int:
    """The upgrade, on a connection (so a test can run it on a throwaway state):
    add the document column, convert every written note, drop the HTML column.
    Returns how many notes were converted. Idempotent."""
    import json

    from app.domains.cms.parse import document_from_trix

    columns = _columns(bind)
    if "notes_document" not in columns:
        bind.execute(sa.text("ALTER TABLE meetings.meeting_items ADD COLUMN notes_document JSONB"))
    if "notes" not in columns:
        return 0
    rows = bind.execute(
        sa.text(
            "SELECT id, notes FROM meetings.meeting_items "
            "WHERE notes IS NOT NULL AND btrim(notes) <> ''"
        )
    ).fetchall()

    def has_words(node) -> bool:
        if isinstance(node, dict):
            if str(node.get("text", "")).strip():
                return True
            return any(has_words(child) for child in node.get("content") or [])
        return False

    written = 0
    for item_id, notes in rows:
        document = document_from_trix(notes)
        # A point that says nothing (`<div><br></div>`) stores nothing, as the save
        # of the new editor does for a blank one (#2038 review B2).
        if not has_words(document):
            continue
        bind.execute(
            sa.text(
                "UPDATE meetings.meeting_items SET notes_document = CAST(:d AS JSONB) WHERE id = :i"
            ),
            {"d": json.dumps(document), "i": item_id},
        )
        written += 1
    bind.execute(sa.text("ALTER TABLE meetings.meeting_items DROP COLUMN notes"))
    return written


def upgrade() -> None:
    log.info("#2023: %s meeting points converted to documents", convert_notes(op.get_bind()))


def downgrade() -> None:
    from app.domains.cms.render import render_document

    bind = op.get_bind()
    columns = _columns(bind)
    if "notes" not in columns:
        bind.execute(sa.text("ALTER TABLE meetings.meeting_items ADD COLUMN notes TEXT"))
    if "notes_document" in columns:
        rows = bind.execute(
            sa.text(
                "SELECT id, notes_document FROM meetings.meeting_items "
                "WHERE notes_document IS NOT NULL"
            )
        ).fetchall()
        for item_id, document in rows:
            bind.execute(
                sa.text("UPDATE meetings.meeting_items SET notes = :n WHERE id = :i"),
                {"n": render_document(document), "i": item_id},
            )
        bind.execute(sa.text("ALTER TABLE meetings.meeting_items DROP COLUMN notes_document"))
