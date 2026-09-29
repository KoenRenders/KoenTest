"""E2E: on /admin/media the activity filter follows the kind (#1291).

Koen: *"Nu zie je bvb. geen sponsors omdat er nog een activiteit als filter staat."*
The filter bar refreshes only the list; the activity list sat outside it, stayed on
the screen after another kind was chosen, and its value travelled along with every
request — so the sponsors came back empty.

Walked in the browser, at 390 and at 1280 px:

1. activity photos, choose an activity → its photo is listed;
2. switch the kind to sponsors → every sponsor is listed, and the activity list is
   gone (count 0), so nothing hidden travels along;
3. switch back to activity photos → the activity list is back, on "Alle
   activiteiten", with the "choose an activity first" state of #891.

And after step 1 the focus is still on the activity list. The list fragment
replaces it out-of-band, and without an `id` htmx cannot put the focus back: it
fell to `<body>` (measured while building, 29 September 2026; the same run with
the id removed fails here with "the focus left the activity list").

It counts before it judges: the sponsor this test creates must be on the screen.

Proven red against master `e1a9a76e` (29 September 2026): a server built from it
failed at step 2 at both widths, with the sponsor missing from the list — the screen
Koen reported.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_als_admin, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def sponsor():
    """A sponsor logo, through the same database as the running server."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.media.api import MediaAsset

    beeld = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    title = f"E2E-sponsor {secrets.token_hex(3)}"
    db = SessionLocal()
    db.add(
        MediaAsset(
            kind="sponsor",
            title=title,
            data=beeld,
            content_type="image/png",
            thumbnail=beeld,
            thumb_content_type="image/png",
            width=64,
            height=64,
            byte_size=len(beeld),
            sort_order=0,
            is_active=True,
        )
    )
    db.commit()
    db.close()
    return title


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _admin(browser, width: int):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    context = browser.new_context(base_url=BASE, viewport={"width": width, "height": 900})
    page = context.new_page()
    login_als_admin(page, email, make_session_value(email))
    return context, page


def _choose(page, name: str, value: str) -> None:
    page.select_option(f'select[name="{name}"]', value)
    htmx_stil(page)


_STATE = """() => {
  const list = document.querySelector('#me-lijst');
  const activity = document.querySelectorAll('select[name="activity_id"]');
  return {
    // The titles sit in the cards' inline-edit fields, so their values count too.
    list: list ? list.innerText + ' ' + [...list.querySelectorAll('input')]
      .map(i => i.value).join(' ') : '',
    activityLists: activity.length,
    activityValue: activity.length ? activity[0].value : null,
    activityVisible: activity.length ? activity[0].getBoundingClientRect().width > 0 : false,
    kind: document.querySelector('select[name="kind"]').value,
    doc: document.documentElement.scrollWidth, vw: window.innerWidth,
  };
}"""


@pytest.mark.parametrize("width", [390, 1280])
def test_the_activity_filter_goes_with_another_kind_and_comes_back_empty(browser, sponsor, width):
    context, page = _admin(browser, width)
    try:
        page.goto("/admin/media?kind=activity_photo")
        pagina_klaar(page)

        # 1. An activity among the activity photos.
        options = page.eval_on_selector_all(
            'select[name="activity_id"] option', "os => os.map(o => o.value).filter(v => v)"
        )
        assert options, "no activity with photos in the seed — the list is not there"
        page.focus('select[name="activity_id"]')
        _choose(page, "activity_id", options[0])
        chosen = page.evaluate(_STATE)
        assert chosen["activityValue"] == options[0], chosen
        assert "E2E-foto" in chosen["list"], f"the activity's photo is not listed: {chosen}"
        # The list you chose from was replaced out-of-band; the focus must be on
        # the new one, not fallen to <body> — a keyboard user would lose their place.
        assert page.evaluate("document.activeElement.name") == "activity_id", (
            f"@{width}: the focus left the activity list after choosing"
        )

        # 2. Another kind: every sponsor, and no activity list left behind.
        _choose(page, "kind", "sponsor")
        sponsors = page.evaluate(_STATE)
        assert sponsor in sponsors["list"], (
            f"@{width}: the sponsor is missing — an activity still filters the list: "
            f"{sponsors['list'][:200]!r}"
        )
        assert sponsors["activityLists"] == 0, f"@{width}: the activity list stayed: {sponsors}"
        assert sponsors["doc"] <= sponsors["vw"], sponsors

        # 3. Back to activity photos: the list is back, on "Alle activiteiten".
        _choose(page, "kind", "activity_photo")
        back = page.evaluate(_STATE)
        assert back["activityLists"] == 1 and back["activityVisible"], back
        assert back["activityValue"] == "", f"@{width}: it came back with an activity: {back}"
        assert "Kies eerst een activiteit" in back["list"], back["list"][:200]
    finally:
        context.close()
