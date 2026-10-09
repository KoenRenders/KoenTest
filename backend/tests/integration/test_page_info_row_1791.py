"""#1791 — a page without an info row can be switched off or given another text.

Every published page is in what Raakje knows, by default, and has no info row
until an administrator says something about it. The screen *Wat Raakje weet*
offered its actions only for a page that had a row, and nothing made one: since
v2.0 a new page could not be taken out of Raakje's knowledge.

A page's actions now go by the page; the row is made at the first use, by the
service. What counts is not the screen but what is sent to the provider, so the
tests read the context that is built.

Proven red, each by one edit that was put back:

- `row.is_active = not row.is_active` taken out of `toggle_page` → the row
  made at the first switch stays on, and an existing row does not turn;
- the row made switched off instead of on in `_page_row` → the first switch
  leaves the page on, and a first text edit takes the page out;
- `page_id=c.page_id` taken out of the template's call → a page without a row
  shows no action, as on `master`.
"""

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.chatbot.context import build_system_prompt
from app.domains.chatbot.models import ChatbotInfo
from app.domains.cms.api import CmsPage
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

PAGE_TEXT = "De kaartavond is elke eerste vrijdag."


@pytest.fixture
def page(db_session):
    # CR-17 (#1671): what Raakje reads of a page is her PUBLISHED DOCUMENT
    # (published_text), no longer her stored HTML — the text is seeded through
    # the doors the app has: save the draft, then publish.
    from app.domains.cms.api import publish, save_document

    page = CmsPage(title="Kaartavond", slug="kaartavond", content=PAGE_TEXT, is_published=True)
    db_session.add(page)
    db_session.commit()
    save_document(
        db_session,
        page.id,
        {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": PAGE_TEXT}]}],
        },
    )
    publish(db_session, page.id)
    return page


@pytest.fixture
def admin(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    client.headers["X-CSRF-Token"] = csrf_token_for(value)
    return client


def _rows(db, page) -> list[ChatbotInfo]:
    db.expire_all()
    return db.query(ChatbotInfo).filter(ChatbotInfo.cms_page_id == page.id).all()


def _block(html: str, page) -> str:
    """The list row of this page, up to the next row."""
    start = html.index(f'data-page="{page.id}"')
    return html[start:].split('<div class="py-2 border-b border-gray-100"')[0]


def test_a_page_without_a_row_shows_the_same_actions_as_one_with_a_row(admin, db_session, page):
    block = _block(admin.get("/admin/ai-context/lijst").text, page)

    assert "standaard" in block, "a page nobody touched reads as the default"
    assert f'hx-post="/admin/ai-context/paginas/{page.id}/toggle"' in block
    assert f'hx-post="/admin/ai-context/paginas/{page.id}/bewerken"' in block
    assert len(re.findall(r'<textarea[^>]*name="text_override"', block)) == 1
    assert len(re.findall(r'<textarea[^>]*name="text_addition"', block)) == 1
    assert "/verwijderen" not in block, "there is no row to remove yet"
    assert "gelezen tekst (OCR)" not in block, "a page is never read by OCR"
    assert _rows(db_session, page) == [], "looking at the screen makes no row"


def test_the_first_switch_makes_the_row_and_takes_the_page_out_of_the_context(
    admin, db_session, page
):
    assert PAGE_TEXT in build_system_prompt(db_session)

    answer = admin.post(f"/admin/ai-context/paginas/{page.id}/toggle")

    assert answer.status_code == 200
    (row,) = _rows(db_session, page)
    assert row.is_active is False
    assert PAGE_TEXT not in build_system_prompt(db_session), (
        "a switched-off page is still sent to the provider"
    )
    block = _block(answer.text, page)
    assert ">uit<" in re.sub(r"\s+", "", block) and "/verwijderen" in block

    admin.post(f"/admin/ai-context/paginas/{page.id}/toggle")
    (row,) = _rows(db_session, page)
    assert row.is_active is True, "the second switch turns the same row on again"
    assert PAGE_TEXT in build_system_prompt(db_session)


def test_a_first_text_replaces_the_page_and_adds_to_it_and_leaves_it_on(admin, db_session, page):
    answer = admin.post(
        f"/admin/ai-context/paginas/{page.id}/bewerken",
        data={"text_override": " Kaarten op vrijdag. ", "text_addition": "Inkom gratis."},
    )

    assert answer.status_code == 200
    (row,) = _rows(db_session, page)
    assert (row.is_active, row.text_override, row.text_addition) == (
        True,
        "Kaarten op vrijdag.",
        "Inkom gratis.",
    )
    prompt = build_system_prompt(db_session)
    assert "Kaarten op vrijdag.\n\nInkom gratis." in prompt
    assert PAGE_TEXT not in prompt, "the replacing text did not replace the page"
    assert ">Kaarten op vrijdag.</textarea>" in _block(answer.text, page), (
        "the form does not show the text that was saved"
    )


def test_empty_texts_read_the_page_itself_again(admin, db_session, page):
    admin.post(
        f"/admin/ai-context/paginas/{page.id}/bewerken",
        data={"text_override": "Iets anders.", "text_addition": ""},
    )
    admin.post(
        f"/admin/ai-context/paginas/{page.id}/bewerken",
        data={"text_override": "  ", "text_addition": ""},
    )

    (row,) = _rows(db_session, page)
    assert (row.text_override, row.text_addition) == (None, None)
    assert PAGE_TEXT in build_system_prompt(db_session)


def test_a_page_that_has_a_row_keeps_that_one_row(admin, db_session, page):
    db_session.add(ChatbotInfo(cms_page_id=page.id, is_active=False, text_addition="Erbij."))
    db_session.commit()

    admin.post(f"/admin/ai-context/paginas/{page.id}/toggle")

    (row,) = _rows(db_session, page)
    assert (row.is_active, row.text_addition) == (True, "Erbij.")


@pytest.mark.parametrize("action", ["toggle", "bewerken"])
def test_a_page_that_is_not_there_answers_404_and_makes_no_row(admin, db_session, action):
    answer = admin.post(f"/admin/ai-context/paginas/999999/{action}", data={"text_override": "x"})

    assert answer.status_code == 404
    assert db_session.query(ChatbotInfo).filter(ChatbotInfo.cms_page_id == 999999).count() == 0
