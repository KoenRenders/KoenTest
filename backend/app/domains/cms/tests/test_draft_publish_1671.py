"""Draft, published, history — the states of a page (CR-17 phase 1, slice 1,
#1671; C6 tests 2, 4 and 6).

Slice 1 is the data layer: nothing on screen changes, but a save under the
still-sitting Trix editor re-derives the documents from `content`, so they
cannot go stale. The core invariants sit at the service level: a save writes
the draft and nothing else; publishing writes exactly one history row and
goes live; restoring writes the draft only.

Every test here can go red: move one assignment from `draft_json` to
`published_json` and they fall over.
"""

import json

from app.domains.cms.api import (
    create_page,
    get_page_by_id,
    get_published_page,
    get_translation,
    publish,
    published_html,
    restore,
    save_document,
    save_draft,
    update_page,
    versions,
)
from app.domains.cms.models import CmsPageHistory
from app.schemas.cms import CmsPageCreate, CmsPageUpdate


def _paragraph(text: str) -> dict:
    """One paragraph of text — the smallest document with words."""
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _page(db_session, **fields):
    defaults = dict(title="Testpagina", slug="testpagina-1671", is_published=False)
    defaults.update(fields)
    return create_page(db_session, CmsPageCreate(**defaults))


def _document(text="Hallo"):
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def test_a_save_writes_the_draft_and_not_the_site(db_session):
    """C6 4: a save leaves `published_json` untouched."""
    page = _page(db_session, is_published=True)
    publish(db_session, page.id, by="first@admins")
    live = get_translation(db_session, page).published_json

    save_draft(db_session, page.id, _document("Gewijzigd"), by="redacteur@admins")

    translation = get_translation(db_session, page)
    assert translation.draft_json["content"][0]["content"][0]["text"] == "Gewijzigd"
    assert translation.published_json == live, "a save changed the live page"
    assert len(versions(db_session, page.id)) == 1, "a save wrote a history row"


def test_publishing_writes_exactly_one_history_row(db_session):
    """C4.3: publish copies draft to published, with exactly one history row
    — the previous version stays restorable."""
    page = _page(db_session)
    save_draft(db_session, page.id, _document(), by="redacteur@admins")
    publish(db_session, page.id, by="redacteur@admins")

    rows = db_session.query(CmsPageHistory).filter(CmsPageHistory.page_id == page.id).all()
    assert len(rows) == 1
    assert rows[0].action == "published"
    assert rows[0].by == "redacteur@admins"
    assert get_page_by_id(db_session, page.id).is_published


def test_restoring_writes_the_draft_and_not_the_site(db_session):
    """C6 6: restoring puts a version back into the DRAFT — the live page
    changes only after publishing again."""
    page = _page(db_session)
    save_draft(db_session, page.id, _document("Versie één"), by="redacteur@admins")
    publish(db_session, page.id, by="redacteur@admins")
    save_draft(db_session, page.id, _document("Versie twee"), by="redacteur@admins")
    publish(db_session, page.id, by="redacteur@admins")
    live = get_translation(db_session, page).published_json

    oldest = versions(db_session, page.id)[-1]
    restore(db_session, page.id, oldest.id, by="redacteur@admins")

    translation = get_translation(db_session, page)
    assert translation.draft_json["content"][0]["content"][0]["text"] == "Versie één"
    assert translation.published_json == live, "restoring changed the live page"
    actions = [v.action for v in versions(db_session, page.id)]
    assert actions.count("restored") == 1


def test_an_unknown_block_is_refused_with_its_name(db_session):
    """C6 2, the gate proven by a violation: a document with a block outside
    the schema is refused with the block's name — never stripped, never
    silently kept. (This is literally AC10's "slider".)"""
    page = _page(db_session)
    document = {
        "type": "doc",
        "content": [{"type": "slider", "attrs": {"beelden": [1, 2]}}],
    }
    try:
        save_draft(db_session, page.id, document, by="redacteur@admins")
    except ValueError as exc:
        assert "slider" in str(exc), f"the block's name is missing in: {exc}"
    else:
        raise AssertionError("an unknown block was kept")
    # The draft is untouched: nothing was stripped or kept.
    assert get_translation(db_session, page).draft_json != document


def test_a_content_update_leaves_the_documents_alone(db_session):
    """Slice 3 (the review's A1, #1734): the derivation of slice 1 — every
    content save re-making the documents — left WITH Trix. The editor writes
    documents; `content` is a page's honest fallback, not her source, and a
    content update may not replace what the author saved."""
    page = _page(db_session, is_published=True, content="<p>Eerste tekst.</p>")
    save_document(
        db_session,
        page.id,
        {"type": "doc", "content": [_paragraph("Wat de redacteur schreef.")]},
    )
    publish(db_session, page.id)
    update_page(
        db_session,
        page.id,
        CmsPageUpdate(content="<p>Tweede tekst met een {{membership_price_full}}.</p>"),
    )
    translation = get_translation(db_session, page)
    texts = [n["text"] for n in translation.draft_json["content"][0]["content"]]
    assert any("Wat de redacteur schreef." in t for t in texts), (
        "a content update replaced the editor's document"
    )
    published = [n["text"] for n in translation.published_json["content"][0]["content"]]
    assert any("Wat de redacteur schreef." in t for t in published), (
        "a content update replaced the published document"
    )


def test_create_page_derives_the_document_from_its_content(db_session):
    """Review C3 (#1673): a page created WITH content gets its documents,
    not an empty draft."""
    page = _page(db_session, content="<p>Meteen inhoud.</p>")
    translation = get_translation(db_session, page)
    texts = [n["text"] for n in translation.draft_json["content"][0]["content"]]
    assert any("Meteen inhoud." in t for t in texts)


def test_the_flag_takes_the_page_offline_and_back(db_session):
    """Slice 3 (the review's A2, #1734): with the checkbox gone from the
    screen, the flag is the JSON door's — and the public route reads her
    (`get_published_page`), so off is off. The published document STAYS:
    a page taken offline and flagged back is live again with the same
    words, no re-publish needed. The SCREEN's way to do this is Koen's to
    decide; this pins the door the flag still has."""
    page = _page(db_session, is_published=True, content="<p>Live tekst.</p>")
    save_document(db_session, page.id, {"type": "doc", "content": [_paragraph("Live document.")]})
    publish(db_session, page.id)
    assert get_translation(db_session, page).published_json is not None

    update_page(db_session, page.id, CmsPageUpdate(is_published=False))
    db_session.expire_all()
    assert get_published_page(db_session, page.slug) is None, "the page is still live"
    assert get_translation(db_session, page).published_json is not None, (
        "the flag destroyed the published document"
    )

    update_page(db_session, page.id, CmsPageUpdate(is_published=True))
    db_session.expire_all()
    assert get_published_page(db_session, page.slug) is not None, "she did not come back"


def test_a_page_without_a_published_document_keeps_serving_her_html(db_session):
    """F11's honest fallback, slice 3's shape. A page whose content never
    converts (a quote) is created with a draft of her words and NO
    published document — the site keeps rendering her stored HTML. A
    content update changes nothing about her documents (A1, #1734): the
    fallback follows `content` while no document is published, and the
    editor's draft stays what it was."""
    page = _page(db_session, is_published=True, content="<blockquote>Een citaat.</blockquote>")
    translation = get_translation(db_session, page)
    assert translation.draft_json is not None, "creation lost her words"
    assert translation.published_json is None, "a quote page does not convert"
    assert "Een citaat." in published_html(db_session, page), "she lost her HTML"

    draft_before = json.dumps(translation.draft_json)
    update_page(
        db_session,
        page.id,
        CmsPageUpdate(content="<blockquote>Een tweede citaat.</blockquote>"),
    )
    db_session.expire_all()
    translation = get_translation(db_session, page)
    assert json.dumps(translation.draft_json) == draft_before, (
        "a content update re-derived the editor's document"
    )
    assert "Een tweede citaat." in published_html(db_session, page), (
        "the fallback no longer follows her content"
    )


def test_the_draft_accepts_a_json_string_and_a_dict(db_session):
    """The editor carries the document as a JSON string; the service accepts
    both shapes without mixing them up."""
    page = _page(db_session)
    save_draft(db_session, page.id, json.dumps(_document()), by="redacteur@admins")
    assert get_translation(db_session, page).draft_json["type"] == "doc"


def test_a_title_change_follows_the_translation_row(db_session):
    """The translation row is the title's source; the page column is its
    shadow that moves along while it exists (C2 cms, one release)."""
    page = _page(db_session)
    update_page(db_session, page.id, CmsPageUpdate(title="Nieuwe titel"))
    translation = get_translation(db_session, page)
    assert translation.title == "Nieuwe titel"
    assert get_page_by_id(db_session, page.id).title == "Nieuwe titel"
