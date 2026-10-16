"""E2E: a file dropped on, or pasted into, the document editor leaves the page where it is
(CR-17 phase 7c, #2023, review B1).

Trix refused a dropped file (`trix-file-accept`); the page editor, the letter and the
meeting notes have no file handler, and a file dropped on a ProseMirror view that has none
is opened by the browser in the tab — the author's unsaved work is left behind. The editor
now stops the default action of a drag over it and a drop on it when the transfer carries
files, and of a paste that carries a file and no text.

Measured, not assumed: the test dispatches the real events with a file in their data
transfer and reads `defaultPrevented` — the signal the browser reads to decide whether it
opens the file. A paste of text must still land in the editor.

Broken on purpose (16 October 2026): the `handleDOMEvents` rule taken out of the editor →
the drop and the paste of a file are red (a drag-over is already stopped by
ProseMirror itself; it stays in the test as the case that must never regress).
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.pages.test_cards_1770 import (  # noqa: E402
    _SETTLE,
    EDITOR,
    _new_page,
    _open,
    _paragraph,
)

#: Dispatches `kind` at the editor with `files` (and `text`) in its transfer and answers
#: whether the page prevented the default action.
_DISPATCH = """([kind, withFile, text]) => {
  const data = new DataTransfer();
  if (withFile) data.items.add(new File(["x"], "foto.png", {type: "image/png"}));
  if (text) data.setData("text/plain", text);
  const target = document.querySelector("#cp-document .tiptap");
  const init = kind === "paste"
    ? {clipboardData: data, bubbles: true, cancelable: true}
    : {dataTransfer: data, bubbles: true, cancelable: true};
  const event = kind === "paste" ? new ClipboardEvent("paste", init) : new DragEvent(kind, init);
  target.dispatchEvent(event);
  return event.defaultPrevented;
}"""


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


@pytest.mark.parametrize("kind", ["dragover", "drop", "paste"])
def test_a_file_never_reaches_the_browser_default(setup, kind):
    browser, session = setup
    page_id, _slug = _new_page(
        f"Bestand {kind}", {"type": "doc", "content": [_paragraph("Boven.")]}
    )
    page = _open(browser, session, page_id, 1280)
    try:
        page.evaluate(_SETTLE)
        page.wait_for_selector(f"{EDITOR} .tiptap")
        before = page.url
        assert page.evaluate(_DISPATCH, [kind, True, ""]) is True, f"a file {kind} is not stopped"
        assert page.url == before
    finally:
        page.context.close()


def test_a_pasted_text_still_lands_in_the_editor(setup):
    """The rule stops files only: a paste of text, with or without a file beside it, is
    still the editor's own (ProseMirror prevents the default itself, so `defaultPrevented`
    cannot tell — the text in the editor can)."""
    browser, session = setup
    page_id, _slug = _new_page("Tekst plakken", {"type": "doc", "content": [_paragraph("Boven.")]})
    page = _open(browser, session, page_id, 1280)
    try:
        page.evaluate(_SETTLE)
        page.locator(f"{EDITOR} .tiptap > p").first.click()
        page.evaluate(_DISPATCH, ["paste", True, "gewone tekst"])
        page.evaluate("() => window.__settle()")
        assert "gewone tekst" in page.locator(f"{EDITOR} .tiptap").inner_text()
    finally:
        page.context.close()
