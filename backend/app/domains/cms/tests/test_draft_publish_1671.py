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

import pytest

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
    save_page_form,
    take_page_offline,
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


def test_offline_halen_writes_a_history_row_and_publiceren_brings_her_back(db_session):
    """The doors the flag has since slice 3 (the review's A2) and the history
    row Koen asked for (8 October 2026: "ja" — the same rule as Publiceren
    and Terugzetten): Offline halen takes her off the site, keeps draft and
    published document, and records who and when; the row is an event, not
    a version (restore refuses her). Publiceren puts the DRAFT live again —
    the draft as she stands then, here the same words because nothing was
    edited in between."""
    from app.domains.cms.models import CmsPageHistory

    page = _page(db_session, is_published=True, content="<p>Live tekst.</p>")
    save_document(db_session, page.id, {"type": "doc", "content": [_paragraph("Live document.")]})
    publish(db_session, page.id, by="redacteur@voorbeeld.example")
    assert get_translation(db_session, page).published_json is not None

    take_page_offline(db_session, page.id, by="beheerder@voorbeeld.example")
    db_session.expire_all()
    assert get_published_page(db_session, page.slug) is None, "the page is still live"
    assert get_translation(db_session, page).published_json is not None, (
        "going offline destroyed the published document"
    )
    row = (
        db_session.query(CmsPageHistory)
        .filter(CmsPageHistory.page_id == page.id, CmsPageHistory.action == "offline")
        .one_or_none()
    )
    assert row is not None, "Offline halen wrote no history row"
    assert row.by == "beheerder@voorbeeld.example", "the row does not say who"
    assert row.document == get_translation(db_session, page).published_json, (
        "the row does not hold the published document of that moment"
    )

    restore_row = (
        db_session.query(CmsPageHistory)
        .filter(CmsPageHistory.page_id == page.id, CmsPageHistory.action == "restored")
        .first()
    )
    assert restore_row is None, "restoring an offline row wrote a restored row"

    publish(db_session, page.id, by="redacteur@voorbeeld.example")
    db_session.expire_all()
    assert get_published_page(db_session, page.slug) is not None, "she did not come back"


def test_restore_refuses_an_offline_row(db_session):
    """An offline row is an event, not a version: Terugzetten refuses her by
    name (the aside shows her without a button; this pins the service door
    the screen calls)."""
    page = _page(db_session, is_published=True, content="<p>Live tekst.</p>")
    save_document(db_session, page.id, {"type": "doc", "content": [_paragraph("Live document.")]})
    publish(db_session, page.id)
    take_page_offline(db_session, page.id, by="beheerder@voorbeeld.example")
    offline_row = (
        db_session.query(CmsPageHistory)
        .filter(CmsPageHistory.page_id == page.id, CmsPageHistory.action == "offline")
        .one()
    )
    import pytest

    with pytest.raises(ValueError, match="geen versie"):
        restore(db_session, page.id, offline_row.id, by="redacteur@voorbeeld.example")


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


def test_create_page_writes_one_translation_row_on_the_app_s_session(_migrate_schema):
    """Red proof of the create screen's "Er ging iets mis" (Koen, 8 October
    2026): the app's sessionmaker runs autoflush=False, the test fixture's
    the SQLAlchemy default (True) — and that difference was the whole bug.
    With autoflush ON, a translation row added earlier in the transaction is
    flushed before the derive step's lookup, so the lookup finds her; with
    autoflush OFF (the app), she stays pending and invisible, the derive
    step created a SECOND row for the same (page, language) and the commit
    died on the primary key. Broken on the old code, this test runs the
    create through a session built exactly like the app's and demands ONE
    row for the page — not a crash, not two.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import sessionmaker

    from app.database import engine
    from app.domains.cms.models import CmsPageTranslation

    connection = engine.connect()
    trans = connection.begin()
    session = sessionmaker(bind=connection, autoflush=False)()
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    try:
        page = create_page(
            session, CmsPageCreate(title="Aanmaaktest", slug="aanmaaktest-appsessie")
        )
        rows = (
            session.query(CmsPageTranslation).filter(CmsPageTranslation.page_id == page.id).count()
        )
        assert rows == 1, "two translation rows were written for one page"
        assert get_translation(session, page).draft_json is not None, (
            "the page was created without a draft document"
        )
    finally:
        event.remove(session, "after_transaction_end", _restart_savepoint)
        session.close()
        trans.rollback()
        connection.close()


class TestTheLiveGoingDoorsValidate:
    """Publish and restore meet the same door as a save (review A3, #1770):
    a draft the migration or a lenient parse left behind, and a history row
    of an older build, cannot go live unread. Every test writes the bad
    document straight into the row — the way only the migration can — and
    each goes red on a publish/restore that skips the door.
    """

    def test_publish_refuses_a_document_with_a_later_phase_node(self, db_session):
        from app.domains.cms.schema import UnknownBlock

        page = _page(db_session)
        translation = save_draft(db_session, page.id, _document("Goed."))
        # The migration's own way of writing: straight into the row.
        translation.draft_json = {
            "type": "doc",
            "content": [{"type": "button", "attrs": {"label": "Klik", "target": "/x"}}],
        }
        db_session.commit()
        with pytest.raises(UnknownBlock):
            publish(db_session, page.id)
        again = get_translation(db_session, page)
        assert again.published_json is None, "a refused publish still went live"

    def test_publish_refuses_a_picture_the_picker_does_not_offer(self, db_session):
        page = _page(db_session)
        translation = save_draft(db_session, page.id, _document("Goed."))
        translation.draft_json = {
            "type": "doc",
            "content": [{"type": "figure", "attrs": {"media_id": 999999, "alt": "Weg."}}],
        }
        db_session.commit()
        from app.domains.cms.schema import InvalidShape

        with pytest.raises(InvalidShape):
            publish(db_session, page.id)

    def test_restore_refuses_a_history_row_the_renderer_cannot_walk(self, db_session):
        from app.domains.cms.models import CmsPageHistory

        page = _page(db_session, is_published=False)
        save_draft(db_session, page.id, _document("Tweede versie."))
        publish(db_session, page.id, by="tester")
        db_session.commit()
        # A history row as an older build might have written her.
        row = db_session.query(CmsPageHistory).filter(CmsPageHistory.page_id == page.id).first()
        row.document = {
            "type": "doc",
            "content": [{"type": "callout", "content": [{"type": "text", "text": "Oud."}]}],
        }
        db_session.commit()
        from app.domains.cms.schema import UnknownBlock

        with pytest.raises(UnknownBlock):
            restore(db_session, page.id, row.id)


def test_a_cell_keeps_her_line_breaks_on_the_site():
    """Enter in a table cell is the author's own line break: two paragraphs
    in a cell ran together as `regel1regel2` on the site (review B1,
    #1770). Goes red on a join with nothing.
    """
    from app.domains.cms.render import render_document

    document = {
        "type": "doc",
        "content": [
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "attrs": {"section": "body"},
                        "content": [
                            {
                                "type": "tableCell",
                                "content": [
                                    _paragraph("Regel een."),
                                    _paragraph("Regel twee."),
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    html = render_document(document)
    assert "Regel een.<br>Regel twee." in html


def test_the_chatbot_keeps_a_word_split_over_two_marks():
    """A word typed and then partly bolded arrives as two text nodes; the
    chatbot's text walker joined them with a space — 'wo rd' (review B2,
    #1770). Goes red on the space-join.
    """
    from app.domains.cms.render import render_document

    document = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "wo"},
                    {"type": "text", "marks": [{"type": "bold"}], "text": "ord"},
                ],
            }
        ],
    }
    text = render_document(document, target="text")
    assert "woord" in text, f"the text walker lost the word: {text!r}"


def test_the_chatbot_walks_a_nested_list():
    """A list inside a list item lost her words in the chatbot's read
    (review B2, #1770). Goes red on the inline-only walker.
    """
    from app.domains.cms.render import render_document

    document = {
        "type": "doc",
        "content": [
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            _paragraph("Bovenpunt."),
                            {
                                "type": "bulletList",
                                "content": [
                                    {
                                        "type": "listItem",
                                        "content": [_paragraph("Onderpunt.")],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    text = render_document(document, target="text")
    assert "Onderpunt." in text


def test_a_title_longer_than_her_column_is_refused_in_words(db_session):
    """`page_translations.title` carries 200 characters; a longer title
    aborted the save on the INSERT (review B3, #1770). Goes red on the
    missing check — and carries Dutch words, not Python's. With a
    document in the same save: the refusal comes before the document is
    written, so the draft she would replace is untouched (the second
    read's finding 2, #1770).
    """
    page = _page(db_session)
    save_draft(db_session, page.id, _document("Het bestaande concept."))
    with pytest.raises(ValueError) as refusal:
        save_page_form(
            db_session,
            page.id,
            CmsPageUpdate(
                title="T" * 201,
                slug=page.slug,
                show_in_nav=False,
                is_home=False,
                show_in_footer=False,
            ),
            json.dumps(_document("De nieuwe tekst.")),
        )
    assert "200" in str(refusal.value)
    # The refusal left the draft as she was.
    assert get_translation(db_session, page).draft_json == _document("Het bestaande concept.")


def test_the_slug_refusal_is_dutch(db_session):
    """The slug refusal reaches the author in Dutch (review B4, #1770), at
    every door that speaks her. Goes red on the English `Slug already
    exists` — the two doors carry the same words.
    """
    page = _page(db_session)
    other = create_page(db_session, CmsPageCreate(title="Andere", slug="andere-1671"))
    assert other is not None
    with pytest.raises(ValueError) as refusal:
        update_page(db_session, page.id, CmsPageUpdate(slug=other.slug))
    assert "bestaat al" in str(refusal.value)
