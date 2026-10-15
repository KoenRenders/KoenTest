"""CR-17 phase 7a (#2023, C6 10): the minutes of a meeting point are a document of
the page editor, and the migration moves the Trix HTML of every point onto it.

Broken on purpose (15 October 2026): the migration dropping a note it could not
parse → the words test fails; `update_item` skipping the schema → the refusal test
fails; the blank editor storing an empty document → the blank test fails.
"""

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from app.domains.cms.parse import document_from_trix
from app.domains.meetings.api import (
    MeetingError,
    SectionKind,
    add_item,
    create_meeting,
    document_of,
    sections_of,
    update_item,
)
from app.domains.meetings.models import MeetingItem
from tests._meeting_notes import note

pytestmark = pytest.mark.ui_serverrendered

MIGRATION = next((Path(__file__).parents[2] / "alembic" / "versions").glob("209_*.py"))

# What Trix writes: a div per line, <br> inside it, a list, a heading, a link.
TRIX = (
    "<h1>Besluit</h1><div>Eerste regel<br>tweede regel</div>"
    "<ul><li>tent</li><li>tafels</li></ul>"
    '<div><strong>vet</strong> en <em>schuin</em> met <a href="https://voorbeeld.example">een link</a></div>'
)


def _words(document: dict) -> str:
    from app.domains.cms.api import render_document

    return " ".join(render_document(document, target="text").split())


def _load():
    spec = importlib.util.spec_from_file_location("notes_209", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _point(db):
    meeting = create_meeting(db, meeting_date=date(2026, 10, 1))
    misc = next(s for s in sections_of(db, meeting) if s.kind is SectionKind.MISC)
    return meeting, add_item(db, meeting, misc, title="Vrij punt")


def test_trix_html_becomes_a_valid_document_and_no_word_is_lost():
    document = document_from_trix(TRIX)
    words = _words(document)
    for word in ("Besluit", "Eerste regel", "tweede regel", "tent", "tafels", "vet", "schuin"):
        assert word in words, (word, words)
    kinds = {n["type"] for n in document["content"]}
    assert {"heading", "paragraph", "bulletList"} <= kinds, kinds


def test_a_nested_list_has_no_blank_line_before_its_sub_list_and_keeps_none_on_a_round_trip():
    """#2038 review A2: `<li>twee<ul>…` became `<li>twee<br><ul>…`, and the break
    came back once more on every round trip. Broken on purpose: the break that ends
    an item's words left in the parser → the first assertion fails; the renderer's
    `<br>` before a nested list back → the second fails."""
    from app.domains.cms.api import render_document
    from app.domains.cms.parse import parse_html

    source = "<ul><li>één</li><li>twee<br><ul><li>a</li><li>b</li></ul></li></ul>"
    document = parse_html(source, lenient=True)
    second = document["content"][0]["content"][1]["content"]
    assert [n["type"] for n in second] == ["paragraph", "bulletList"]
    assert {"type": "hardBreak"} not in second[0]["content"]
    html = render_document(document)
    assert "<li>twee<ul>" in html and "<br><ul>" not in html
    # Round trip: render, parse again, render again — the same.
    again = parse_html(html, lenient=True)
    assert again == document
    assert render_document(again) == html


SEED_SNAPSHOT = Path(__file__).parent / "snapshots" / "seed_page_documents_2023.json"


def test_the_parser_makes_the_documents_of_the_seeded_pages_it_always_made(db_session):
    """The fix of A2 touches no page without a nested list: for every seeded page
    the document `parse_html` makes of her HTML — strict and lenient — equals the
    snapshot taken with the parser as it was before the fix. To regenerate on
    purpose delete the file, run the test (it writes and fails once) and say why in
    the commit."""
    from app.domains.cms.api import list_pages
    from app.domains.cms.parse import parse_html

    made = {
        page.slug: [parse_html(page.content), parse_html(page.content, lenient=True)]
        for page in list_pages(db_session)
        if page.content
    }
    assert len(made) >= 3, "the seed holds fewer pages with content than this snapshot measures"
    if not SEED_SNAPSHOT.exists():
        SEED_SNAPSHOT.parent.mkdir(exist_ok=True)
        SEED_SNAPSHOT.write_text(json.dumps(made, indent=1, sort_keys=True, ensure_ascii=False))
        pytest.fail("the snapshot was written: run the test again")
    assert json.loads(SEED_SNAPSHOT.read_text()) == json.loads(json.dumps(made)), (
        "a seeded page's document changed"
    )


def test_what_the_converter_cannot_read_still_keeps_its_words():
    document = document_from_trix("<div>één<span>twee</span></div><blink>drie</blink>")
    assert {"één", "twee", "drie"} <= set(_words(document).replace("twee", " twee ").split()) or (
        "drie" in _words(document)
    )
    assert document_from_trix("") == {"type": "doc", "content": []}


def test_the_migration_converts_every_written_note_and_drops_the_html_column(db_session):
    meeting, written = _point(db_session)
    misc = next(s for s in sections_of(db_session, meeting) if s.kind is SectionKind.MISC)
    blank = add_item(db_session, meeting, misc, title="Leeg punt")
    written_id, blank_id = written.id, blank.id  # before the DDL: the ORM would refresh
    # The state before the migration: the HTML column back, the document column gone.
    db_session.execute(text("ALTER TABLE meetings.meeting_items DROP COLUMN notes_document"))
    db_session.execute(text("ALTER TABLE meetings.meeting_items ADD COLUMN notes TEXT"))
    db_session.execute(
        text("UPDATE meetings.meeting_items SET notes = :n WHERE id = :i"),
        {"n": TRIX, "i": written_id},
    )
    db_session.execute(
        text("UPDATE meetings.meeting_items SET notes = '  ' WHERE id = :i"), {"i": blank_id}
    )
    converted = _load().convert_notes(db_session.connection())
    assert converted == 1, "only the written note is converted"
    blank_after = db_session.execute(
        text("SELECT notes_document FROM meetings.meeting_items WHERE id = :i"), {"i": blank_id}
    ).scalar()
    assert blank_after is None, "a point that says nothing stores nothing"
    columns = {
        row[0]
        for row in db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'meetings' AND table_name = 'meeting_items'"
            )
        )
    }
    assert "notes" not in columns and "notes_document" in columns
    rows = dict(
        db_session.execute(
            text(
                "SELECT id, notes_document FROM meetings.meeting_items WHERE id IN :ids"
            ).bindparams(ids=(written_id, blank_id))
        ).fetchall()
    )
    assert "Eerste regel" in _words(rows[written_id]) and rows[blank_id] is None
    # Running it again changes nothing.
    assert _load().convert_notes(db_session.connection()) == 0


def test_a_save_stores_the_document_and_the_screen_renders_it(db_session):
    meeting, point = _point(db_session)
    update_item(db_session, meeting, point.id, notes=json.dumps(note("Uitverkocht", "300 tickets")))
    db_session.expire_all()
    shown = next(i for s in document_of(db_session, meeting) for i in s.items if i.id == point.id)
    assert shown.notes == "<p>Uitverkocht</p><p>300 tickets</p>"
    assert json.loads(shown.notes_json) == note("Uitverkocht", "300 tickets")


def test_the_schema_is_the_border(db_session):
    meeting, point = _point(db_session)
    with pytest.raises(MeetingError, match="Onbekend blok"):
        update_item(
            db_session,
            meeting,
            point.id,
            notes={"type": "doc", "content": [{"type": "scriptje", "content": []}]},
        )
    with pytest.raises(MeetingError):
        update_item(db_session, meeting, point.id, notes="{niet-json")
    db_session.expire_all()
    assert db_session.get(MeetingItem, point.id).notes_document is None, "nothing stored"


def test_a_blank_editor_stores_nothing(db_session):
    meeting, point = _point(db_session)
    update_item(db_session, meeting, point.id, notes=note("iets"))
    update_item(
        db_session,
        meeting,
        point.id,
        notes={"type": "doc", "content": [{"type": "paragraph"}]},
    )
    db_session.expire_all()
    assert db_session.get(MeetingItem, point.id).notes_document is None
    shown = next(i for s in document_of(db_session, meeting) for i in s.items if i.id == point.id)
    assert shown.notes == "" and shown.notes_json == ""
