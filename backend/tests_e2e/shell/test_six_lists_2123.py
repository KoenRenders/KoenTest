"""E2E: six lists on the kit's list page (#2123), at 390 and 1 100 px.

Formulieren, Vergaderingen, Nieuwsbrieven, Pagina's, Design Studio and Rapporten are the
kit's table with its toolbar. Read from the rendered page, per list:

- the page is no wider than the window, at both widths (the table stacks into cards under
  900 px: no sideways scroll);
- the search narrows the rows to the one that holds the word, and the segment narrows them
  to its own (Vergaderingen: Komende; Pagina's: Concept);
- the main action of each list still works: a row opens its record, "Nieuwe nieuwsbrief"
  makes a draft and opens it, an order arrow moves a page, "Deellink kopiëren" and
  "Instellingen"/"Abonnees" are under the menu and not beside the title.

Broken on purpose (18 October 2026): the toolbar's `hx_target` of the list pointing at
nothing → the search stood still and every narrowing test was red.

Rows are made for this file (tagged `Lijst2123`) and stay: the e2e database is fresh per run.
"""

import os
import re
import secrets
import sys
from datetime import timedelta

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.kernel.clock import belgian_today  # noqa: E402
from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

TAG = "Lijst2123"
ROWS = "[data-table-frame] tbody tr[data-row]"
SIDEWAYS = "document.documentElement.scrollWidth - innerWidth"


def _seed() -> dict:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate, ActivityStatus
    from app.domains.cms.api import create_page
    from app.domains.designstudio.service import create_design
    from app.domains.forms.models import Form
    from app.domains.meetings.service import create_meeting
    from app.domains.newsletter.models import Newsletter
    from app.schemas.cms import CmsPageCreate

    db = SessionLocal()
    try:
        made = {}
        for title in (f"{TAG} Enquête", f"{TAG} Aanmelding"):
            db.add(Form(title=title, status="open", share_token=secrets.token_hex(8)))
        today = belgian_today()
        made["next"] = create_meeting(
            db, meeting_date=today + timedelta(days=20), location=f"{TAG} Zaal"
        ).id
        made["past"] = create_meeting(
            db, meeting_date=today - timedelta(days=20), location=f"{TAG} Kerk"
        ).id
        first = create_page(db, CmsPageCreate(title=f"{TAG} Eerste", slug="lijst2123-eerste"))
        create_page(db, CmsPageCreate(title=f"{TAG} Tweede", slug="lijst2123-tweede"))
        made["first_page"] = first.id
        db.add(Newsletter(subject=f"{TAG} Brief", created_by="e2e@example.com"))
        activity = Activity(name=f"{TAG} Wandeling", status=ActivityStatus.DRAFT)
        db.add(activity)
        db.flush()
        db.add(ActivityDate(activity_id=activity.id, start_date=today + timedelta(days=9)))
        db.commit()
        create_design(db, activity_id=activity.id, duo_code="dark_green-golden_yellow")
        db.commit()
        return made
    finally:
        db.close()


@pytest.fixture(scope="module")
def world():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    made = _seed()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), made
        b.close()


def _open(world, path: str, width: int):
    browser, session, _made = world
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session)
    page.goto(path)
    pagina_klaar(page)
    return page


def _titles(page) -> list[str]:
    return [t.strip() for t in page.locator(f"{ROWS} [data-row-link]").all_inner_texts()]


LISTS = [
    "/admin/formulieren",
    "/admin/vergaderingen",
    "/admin/nieuwsbrieven",
    "/admin/paginas",
    "/admin/ontwerpen",
    "/admin/rapporten",
]


@pytest.mark.parametrize("width", [390, 1100])
@pytest.mark.parametrize("path", LISTS)
def test_the_list_is_no_wider_than_the_window(world, path, width):
    page = _open(world, path, width)
    try:
        assert page.locator("[data-list-head] h1").count() == 1
        assert page.locator("[data-toolbar]").count() == 1
        assert page.locator("[data-table-frame]").count() == 1, "the list is not the kit's table"
        assert page.evaluate(SIDEWAYS) <= 0, (path, width)
    finally:
        page.close()


def _search(page, word: str):
    page.fill("input[type=search]", word)
    page.wait_for_function(
        "(w) => ![...document.querySelectorAll('[data-table-frame] [data-row-link]')]"
        ".some(a => !a.textContent.includes(w)) || !document.querySelector('[data-table-frame]')",
        arg=word,
        timeout=10000,
    )


@pytest.mark.parametrize(
    ("path", "word", "expected"),
    [
        ("/admin/formulieren", f"{TAG} Enquête", f"{TAG} Enquête"),
        ("/admin/paginas", f"{TAG} Tweede", f"{TAG} Tweede"),
        ("/admin/ontwerpen", f"{TAG} Wandeling", f"{TAG} Wandeling"),
        ("/admin/nieuwsbrieven", "zzz-geen-brief", None),
    ],
)
def test_the_search_narrows_the_rows(world, path, word, expected):
    page = _open(world, path, 1100)
    try:
        page.fill("input[type=search]", word)
        if expected is None:
            page.wait_for_selector("[data-table-frame]", state="detached", timeout=10000)
            expect(page.get_by_text("gevonden")).to_be_visible()
        else:
            page.wait_for_function(
                "(n) => document.querySelectorAll('[data-table-frame] tbody tr[data-row]').length === n",
                arg=1,
                timeout=10000,
            )
            assert _titles(page) == [expected]
    finally:
        page.close()


def test_the_segment_narrows_vergaderingen_and_pagina_s(world):
    _browser, _session, made = world
    page = _open(world, "/admin/vergaderingen", 1100)
    try:
        page.locator("[data-status-filter] label", has_text="Komende").click()
        past = f'a[href="/admin/vergaderingen/{made["past"]}"]'
        page.wait_for_function("(sel) => !document.querySelector(sel)", arg=past, timeout=10000)
        assert page.locator(f'a[href="/admin/vergaderingen/{made["next"]}"]').count() == 1
    finally:
        page.close()
    page = _open(world, "/admin/paginas", 1100)
    try:
        everyone = page.locator(ROWS).count()
        page.locator("[data-status-filter] label", has_text="Concept").click()
        page.wait_for_function(
            "() => [...document.querySelectorAll('[data-table-frame] tbody tr[data-row]')]"
            ".every(tr => tr.textContent.includes('concept'))",
            timeout=10000,
        )
        assert 2 <= page.locator(ROWS).count() <= everyone
    finally:
        page.close()


def test_a_row_opens_its_record(world):
    _browser, _session, made = world
    for path, link, pattern in (
        ("/admin/formulieren", f"{TAG} Enquête", r"/admin/formulieren/\d+$"),
        ("/admin/vergaderingen", None, rf"/admin/vergaderingen/{made['next']}$"),
        ("/admin/paginas", f"{TAG} Eerste", rf"/admin/paginas/{made['first_page']}$"),
        ("/admin/ontwerpen", f"{TAG} Wandeling", r"/admin/ontwerpen/\d+$"),
    ):
        page = _open(world, path, 1100)
        try:
            row = page.locator(ROWS, has_text=link) if link else page.locator(ROWS, has_text="Zaal")
            row.first.locator("[data-row-link]").click()
            page.wait_for_url(re.compile(pattern), timeout=15000)
        finally:
            page.close()


def test_a_new_letter_is_made_and_opened_and_the_extras_stand_under_the_menu(world):
    page = _open(world, "/admin/nieuwsbrieven", 1100)
    try:
        head = page.locator("[data-list-head]").inner_text()
        assert "Instellingen" not in head and "Abonnees" not in head
        page.locator("[data-more-button]").click()
        menu = page.locator("[data-more-menu]")
        expect(menu.get_by_text("Instellingen")).to_be_visible()
        expect(menu.get_by_text("Abonnees")).to_be_visible()
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Nieuwe nieuwsbrief").click()
        page.wait_for_url(re.compile(r"/admin/nieuwsbrieven/\d+(\?bewerken=1)?$"), timeout=15000)
    finally:
        page.close()


def test_an_order_arrow_moves_a_page_and_the_share_link_stands_under_the_row_menu(world):
    page = _open(world, "/admin/paginas", 390)
    try:
        before = _titles(page)
        mine = [t for t in before if t.startswith(TAG)]
        assert len(mine) == 2, before
        first_row = page.locator(ROWS, has_text=mine[0])
        box = first_row.locator('button[aria-label="Naar onder"]').bounding_box()
        assert box["width"] >= 44 and box["height"] >= 44, f"the arrow is {box}, not 44 px"
        first_row.locator('button[aria-label="Naar onder"]').click()
        page.wait_for_function(
            "(t) => { const r = [...document.querySelectorAll('[data-row-link]')].map(a => a.textContent.trim());"
            " return r.indexOf(t[1]) < r.indexOf(t[0]); }",
            arg=mine,
            timeout=10000,
        )
    finally:
        page.close()
    page = _open(world, "/admin/formulieren", 1100)
    try:
        row = page.locator(ROWS, has_text=f"{TAG} Enquête").first
        row.locator("[data-row-menu-trigger]").click()
        expect(row.get_by_role("menuitem", name="Deellink kopiëren")).to_be_visible()
    finally:
        page.close()
