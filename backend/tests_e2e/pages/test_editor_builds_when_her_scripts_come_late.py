"""E2E: the editor builds when her scripts come after the last swap (CR-17
#1679, review M1 of 12 October 2026).

A page reached through a boosted link — the page list to a page record,
the author's own way in — brings the editor's two scripts inside the
swapped fragment, as her own requests, and they run in the network's
order, not the tags'. Before the repair the script built only at
`DOMContentLoaded` (long past) and `htmx:afterSwap` (past too: the swap
that carried her is done before she runs), so the editor built only when
a LATER swap of something else happened to land after her scripts — some
35 ms of margin on a fast machine, and nothing at all on a slow line. The
red run of 12 October 2026 was exactly this walk, in a browser with an
empty cache.

Each pin holds ONE of the two scripts back through the test's own route
and walks list → page:

- the vendor held back, and released only once the LAST swap (the
  picture picker's own fragment) has landed: the library's arrival must
  build the editor herself — on the old code the picker's swap closed
  the door (ready without the library) and the release built nothing;
- `document-editor.js` held back, and released once the mount stands:
  her own run must build what the page holds — on the old code she only
  registered her listeners and the mount stayed empty.

No clock anywhere: the waits are on selectors and on the held route.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie  # noqa: E402

# `statisch()` hangs a cache hash behind every static file (`?v=…`), so the
# glob keeps her tail open.
VENDOR = "**/vendor/tiptap-3.31.4.min.js*"
EDITOR_SCRIPT = "**/document-editor.js*"
#: The figure dialog's picture picker (`revealed once`): the last swap the
#: page record fires on her own — on the old code the only thing that
#: built the editor after the fragment, with some 35 ms to spare.
PICKER = "#mp-cp-document-figuur > *"


@pytest.fixture(scope="module")
def setup():
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import CmsPage
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = SessionLocal()
    page = CmsPage(
        title="Trage scripts",
        slug=f"trage-scripts-{tag}",
        content="<p>De woorden die er vandaag staan.</p>",
        is_published=True,
    )
    db.add(page)
    db.commit()
    page_id = page.id
    db.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, page_id, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _list_to_page_record(page):
    """The author's own way in (M1): the page list, then a boosted link to
    the first record — the swap that carries the editor's scripts is past
    when they run. Waited on the mount alone, not on the editor: whether
    she builds from the held script is what the pins ask."""
    page.goto("/admin/paginas")
    htmx_stil(page)
    page.locator("a[href^='/admin/paginas/']:not([href$='/nieuw'])").first.click()
    page.wait_for_selector("[data-document-editor]", state="attached", timeout=10000)


def _pin(b, session, vastgehouden, wacht_voor_loslaten):
    """One held script, the author's walk, then the release: the editor
    must stand built after her — never from a later swap of something
    else. Red on the tip before the repair: the mount stayed empty until
    the selector's timeout."""
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    vast = []
    page.route(vastgehouden, lambda route: vast.append(route))
    try:
        login_met_sessie(page, session)
        _list_to_page_record(page)
        if wacht_voor_loslaten:
            page.wait_for_selector(wacht_voor_loslaten, state="attached", timeout=10000)
        assert vast, "the held request never came"
        # De vastgehouden script komt nu pas — de editor bouwt uit zichzelf.
        for route in vast:
            route.continue_()
        page.wait_for_selector(".document-editor .tiptap", timeout=10000)
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def test_the_vendor_library_herself_builds_the_editor(setup):
    """The vendor arrives after the last swap: her `load` builds what the
    page holds. On the old code the picker's swap had closed the door —
    ready without the library — and the arrival built nothing."""
    b, _page_id, session = setup
    _pin(b, session, VENDOR, PICKER)


def test_the_editors_own_run_builds_the_editor(setup):
    """`document-editor.js` arrives after the page record stands: her own
    run builds what she finds. On the old code she only registered her
    listeners and the mount stayed empty."""
    b, _page_id, session = setup
    _pin(b, session, EDITOR_SCRIPT, None)
