"""E2E: a section is removed from its own bar (#2171, CR-32).

A page of three sections: the first, the middle and the last are removed one by
one, the stored page lacks exactly that section; Ctrl+Z brings a removed one
back whole (tone, eyebrow and content); the only block of a page can go and the
page still saves; the button is a named button, reachable with Tab; at 390 px the
bar stays inside the editor.

Broken on purpose (19 October 2026): the delete range of the click handler cut to
nothing (`tr.delete(pos, pos)`) → nothing is removed and five tests are red.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

EDITOR = "#cp-document"
NAMES = ["Een", "Twee", "Drie"]


def _par(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _section(name: str, tone: str) -> dict:
    return {
        "type": "section",
        "attrs": {"tone": tone, "eyebrow": name},
        "content": [_par(f"Tekst van {name}.")],
    }


@pytest.fixture(scope="module")
def setup():
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import CmsPage, save_document
    from app.domains.cms.service import create_page
    from app.schemas.cms import CmsPageCreate
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = SessionLocal()
    ids = []

    def make(label: str, content: list) -> int:
        page = create_page(db, CmsPageCreate(title=f"Sectie {label}", slug=f"sv-{label}-{tag}"))
        save_document(db, page.id, {"type": "doc", "content": content})
        ids.append(page.id)
        return page.id

    pages = {
        label: make(
            label, [_section(n, tone) for n, tone in zip(NAMES, ("tint", "accent", "plain"))]
        )
        for label in ("een", "twee", "drie", "ongedaan", "toets")
    }
    pages["enige"] = make("enige", [_section("Enige", "tint")])
    db.commit()
    db.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, pages, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()
    cleanup = SessionLocal()
    try:
        cleanup.query(CmsPage).filter(CmsPage.id.in_(ids)).delete(synchronize_session=False)
        cleanup.commit()
    finally:
        cleanup.close()


def _open(setup, label: str, width: int = 1440):
    b, pages, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session)
    page.goto(f"/admin/paginas/{pages[label]}")
    pagina_klaar(page)
    page.wait_for_selector(f"{EDITOR} .tiptap .prose-section")
    return page, pages[label]


def _save(page, page_id: int) -> None:
    page.locator("[data-action-bar] button[data-form-save]").click()
    page.wait_for_url(f"**/admin/paginas/{page_id}*opgeslagen=1*", timeout=15000)


def _stored(page_id: int) -> list:
    from app.database import SessionLocal
    from app.domains.cms.api import CmsPage, draft_document

    db = SessionLocal()
    try:
        return draft_document(db, db.get(CmsPage, page_id))["content"]
    finally:
        db.close()


def _eyebrows(content: list) -> list:
    return [b["attrs"].get("eyebrow") for b in content if b["type"] == "section"]


def _remove(page, index: int) -> None:
    page.locator(f"{EDITOR} .de-section-remove").nth(index).click()


@pytest.mark.parametrize(("label", "index"), [("een", 0), ("twee", 1), ("drie", 2)])
def test_removing_a_section_removes_exactly_that_one(setup, label, index):
    page, page_id = _open(setup, label)
    gone = NAMES[index]
    try:
        _remove(page, index)
        assert page.locator(f"{EDITOR} .tiptap .prose-section").count() == 2
        _save(page, page_id)
        assert _eyebrows(_stored(page_id)) == [n for n in NAMES if n != gone]
    finally:
        page.close()


def test_ctrl_z_brings_the_section_back_whole(setup):
    page, page_id = _open(setup, "ongedaan")
    try:
        _remove(page, 1)
        assert page.locator(f"{EDITOR} .tiptap .prose-section").count() == 2
        page.keyboard.press("Control+z")
        expect(page.locator(f"{EDITOR} .tiptap .prose-section")).to_have_count(3)
        _save(page, page_id)
        stored = _stored(page_id)
        assert _eyebrows(stored) == NAMES, "one undo restores the whole section"
        middle = stored[1]
        assert middle["attrs"]["tone"] == "accent"
        assert middle["content"][0]["content"][0]["text"] == "Tekst van Twee."
    finally:
        page.close()


def test_the_only_block_can_go_and_the_page_still_saves(setup):
    page, page_id = _open(setup, "enige")
    try:
        _remove(page, 0)
        assert page.locator(f"{EDITOR} .tiptap .prose-section").count() == 0
        assert page.locator(f"{EDITOR} .tiptap > p").count() == 1, "one empty paragraph stays"
        _save(page, page_id)
        assert [b["type"] for b in _stored(page_id)] == ["paragraph"]
    finally:
        page.close()


def test_the_button_is_named_and_reached_with_the_keyboard(setup):
    page, page_id = _open(setup, "toets")
    try:
        button = page.get_by_role("button", name="Sectie verwijderen")
        assert button.count() == 3
        page.locator(f"{EDITOR} .de-section-eyebrow").first.focus()
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.classList.contains('de-section-remove')")
        page.keyboard.press("Enter")
        assert page.locator(f"{EDITOR} .tiptap .prose-section").count() == 2
    finally:
        page.close()


_BAR = """() => { const editor = document.querySelector('#cp-document').getBoundingClientRect();
  const bar = document.querySelector('#cp-document .de-section-bar');
  const r = bar.getBoundingClientRect();
  const kids = [...bar.children].map(c => { const k = c.getBoundingClientRect();
    return {left: Math.round(k.left), right: Math.round(k.right), top: Math.round(k.top)}; });
  return {editorLeft: Math.round(editor.left), editorRight: Math.round(editor.right),
    left: Math.round(r.left), right: Math.round(r.right), height: Math.round(r.height), kids,
    scroll: document.documentElement.scrollWidth === innerWidth}; }"""


@pytest.mark.parametrize("width", [390, 1100])
def test_the_bar_stays_inside_the_editor(setup, width):
    page, _id = _open(setup, "toets", width)
    try:
        seen = page.evaluate(_BAR)
        print("MEASURE section bar", width, seen)
        assert seen["left"] >= seen["editorLeft"] and seen["right"] <= seen["editorRight"], seen
        assert all(k["right"] <= seen["editorRight"] for k in seen["kids"]), seen
        assert seen["scroll"], "the page scrolls sideways"
    finally:
        page.close()
