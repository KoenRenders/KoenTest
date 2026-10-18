"""#2124 — AI-context on the kit's list page, each item a record of its own.

CR-11 phase 5, track 2, round 3: the list's in-row disclosure became a record per
document, page and note, with the same actions — Bewerken, Aan/uit, Opnieuw lezen,
Verwijderen — and the read text. Nothing new.

A record is addressed by its source, so a document or a page without a row of its
own ("standaard") opens too, and looking at it makes no row: the row is made where
it is made today — by the reading job, or at a page's first switch or text (the
master CLI, 18 October 2026, option 1: no write on a GET).

Proven red (put back): the record route made to call `_page_row` for a page →
`test_looking_at_a_page_without_a_row_makes_none` fails on one row.
"""

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.chatbot.models import ChatbotInfo
from app.domains.cms.api import CmsPage
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def admin(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    client.headers["X-CSRF-Token"] = csrf_token_for(value)
    return client


def _document(db, *, row: bool, text: str = "AFFICHE: Zomerbar op 1 juli") -> int:
    from app.domains.media.models import MediaAsset

    asset = MediaAsset(kind="activity_poster", data=b"x", content_type="image/png")
    db.add(asset)
    db.flush()
    if row:
        db.add(ChatbotInfo(media_asset_id=asset.id, is_active=True, extracted_text=text))
    db.commit()
    return asset.id


def _page(db) -> int:
    page = CmsPage(title="Kaartavond", slug="kaartavond", content="x", is_published=True)
    db.add(page)
    db.commit()
    return page.id


def _rows(db) -> int:
    db.expire_all()
    return db.query(ChatbotInfo).count()


def _flat(html: str) -> str:
    return re.sub(r"\s+", "", html)


def test_each_segment_lists_its_items_and_links_their_records(admin, db_session):
    asset_id = _document(db_session, row=True)
    page_id = _page(db_session)
    note = ChatbotInfo(title="Parkeren", text_addition="Aan de kerk.", is_active=False)
    db_session.add(note)
    db_session.commit()

    documents = admin.get("/admin/ai-context").text
    assert f'href="/admin/ai-context/documenten/{asset_id}?terug=' in documents
    assert ">Actief<" in _flat(documents)

    pages = admin.get("/admin/ai-context?segment=paginas").text
    assert f'href="/admin/ai-context/paginas/{page_id}?terug=' in pages
    assert ">Standaard<" in _flat(pages), "a page without a row is on by default"

    notes = admin.get("/admin/ai-context?segment=notities").text
    assert f'href="/admin/ai-context/notities/{note.id}?terug=' in notes
    assert ">Uit<" in _flat(notes)
    assert 'href="/admin/ai-context/notities/nieuw"' in notes, "+ Notitie"
    assert 'href="/admin/ai-context/notities/nieuw"' not in documents


def test_the_search_keeps_what_matches(admin, db_session):
    for title in ("Parkeren", "Openingsuren"):
        db_session.add(ChatbotInfo(title=title, text_addition="x"))
    db_session.commit()
    found = admin.get("/admin/ai-context/lijst?segment=notities&q=park").text
    assert "Parkeren" in found and "Openingsuren" not in found


def test_a_document_with_a_row_offers_what_its_row_offered(admin, db_session):
    asset_id = _document(db_session, row=True)
    row = db_session.query(ChatbotInfo).filter(ChatbotInfo.media_asset_id == asset_id).one()
    record = admin.get(f"/admin/ai-context/documenten/{asset_id}").text

    assert "AFFICHE: Zomerbar op 1 juli" in record, "the read text"
    assert f'href="/admin/ai-context/documenten/{asset_id}?bewerken=1"' in record
    assert f'hx-post="/admin/ai-context/{row.id}/toggle"' in record
    assert f'hx-post="/admin/ai-context/documenten/{asset_id}/opnieuw-lezen"' in record
    assert f'hx-post="/admin/ai-context/{row.id}/verwijderen"' in record
    assert "data-confirm=" in record


def test_looking_at_a_document_without_a_row_makes_none(admin, db_session):
    """A "standaard" document opens a record, with what it had: Opnieuw lezen and
    "nog niets gelezen" — no Bewerken, Aan/uit or Verwijderen without a row."""
    asset_id = _document(db_session, row=False)
    before = _rows(db_session)

    record = admin.get(f"/admin/ai-context/documenten/{asset_id}")
    assert record.status_code == 200
    assert ">Standaard<" in _flat(record.text)
    assert "nog niets gelezen" in record.text
    assert f'hx-post="/admin/ai-context/documenten/{asset_id}/opnieuw-lezen"' in record.text
    assert "?bewerken=1" not in record.text
    assert "/toggle" not in record.text and "/verwijderen" not in record.text
    assert _rows(db_session) == before, "looking made no row"


def test_looking_at_a_page_without_a_row_makes_none(admin, db_session):
    page_id = _page(db_session)
    before = _rows(db_session)
    for suffix in ("", "?bewerken=1"):
        assert admin.get(f"/admin/ai-context/paginas/{page_id}{suffix}").status_code == 200
    assert _rows(db_session) == before, "looking made no row"


def test_a_note_is_edited_switched_and_deleted_on_its_record(admin, db_session):
    made = admin.post(
        "/admin/ai-context/notities",
        data={"title": "Parkeren", "text_addition": "Aan de kerk."},
        follow_redirects=False,
    )
    assert made.status_code == 303
    note = db_session.query(ChatbotInfo).filter(ChatbotInfo.title == "Parkeren").one()
    assert made.headers["location"] == f"/admin/ai-context/notities/{note.id}"

    form = admin.get(f"/admin/ai-context/notities/{note.id}?bewerken=1").text
    assert f'hx-post="/admin/ai-context/{note.id}/bewerken"' in form
    saved = admin.post(
        f"/admin/ai-context/{note.id}/bewerken",
        data={"title": "Parkeren", "text_addition": "Aan de kerk en op het plein."},
        follow_redirects=False,
    )
    assert saved.headers["location"] == f"/admin/ai-context/notities/{note.id}"
    db_session.expire_all()
    assert note.text_addition == "Aan de kerk en op het plein."

    switched = admin.post(f"/admin/ai-context/{note.id}/toggle", follow_redirects=False)
    assert switched.headers["location"] == f"/admin/ai-context/notities/{note.id}"
    db_session.expire_all()
    assert note.is_active is False

    gone = admin.post(
        f"/admin/ai-context/{note.id}/verwijderen",
        data={"segment": "notities"},
        follow_redirects=False,
    )
    assert gone.headers["location"] == "/admin/ai-context?segment=notities"
    assert db_session.query(ChatbotInfo).filter(ChatbotInfo.id == note.id).first() is None


def test_read_again_comes_back_on_the_document(admin, db_session):
    asset_id = _document(db_session, row=True)
    answer = admin.post(
        f"/admin/ai-context/documenten/{asset_id}/opnieuw-lezen", follow_redirects=False
    )
    assert answer.status_code == 303
    assert answer.headers["location"] == f"/admin/ai-context/documenten/{asset_id}"


def test_an_unknown_item_or_kind_is_a_404(admin, db_session):
    assert admin.get("/admin/ai-context/documenten/999999").status_code == 404
    assert admin.get("/admin/ai-context/notities/999999").status_code == 404
    assert admin.get("/admin/ai-context/iets/1").status_code == 404
