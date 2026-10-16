"""E2E: a page's address that the application answers on is refused where it is typed (#2061).

In a browser at 390 px, because the promise is a place on the screen: on the page's
record the reason stands under the Webadres field, in line with it and below it,
and the banner at the top says which field to look at; on Nieuwe pagina the reason
stands in the form's message line, where a 400 used to show only the general
"something went wrong".
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

PRINTS = os.environ.get("E2E_PRINTS")
REASON = "/activiteiten is een adres van de toepassing zelf"


@pytest.fixture(scope="module")
def setup():
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import create_page
    from app.schemas.cms import CmsPageCreate
    from tests.conftest import SEEDED_ADMIN_EMAIL

    db = SessionLocal()
    page = create_page(
        db, CmsPageCreate(title="Adresproef", slug=f"adresproef-{secrets.token_hex(3)}")
    )
    page_id = page.id
    db.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, page_id, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _print(page, name: str) -> None:
    if PRINTS:
        os.makedirs(PRINTS, exist_ok=True)
        page.screenshot(path=os.path.join(PRINTS, name), full_page=False)


def test_the_record_shows_the_reason_under_the_address_field(setup):
    b, page_id, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.locator("#cp-slug").fill("activiteiten")
        page.locator("[data-form-save]").first.click()
        error = page.locator("#cp-slug-error")
        expect(error).to_contain_text(REASON)
        expect(page.get_by_role("alert").first).to_contain_text("controleer 1 veld")
        error.scroll_into_view_if_needed()
        field = page.locator("#cp-slug").bounding_box()
        reason = error.bounding_box()
        wide = page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        print("MEASURE field", field, "reason", reason)
        assert reason["y"] >= field["y"] + field["height"], "the reason stands under the field"
        assert abs(reason["x"] - field["x"]) <= 1, "the reason starts where the field starts"
        assert reason["x"] + reason["width"] <= 390, "the reason fits the phone"
        assert wide, "the record scrolls sideways at 390 px"
        assert page.locator("#cp-slug").get_attribute("aria-invalid") == "true"
        assert page.locator("#cp-slug").input_value() == "activiteiten", (
            "the field keeps what was typed"
        )
        _print(page, "record-390.png")
    finally:
        page.close()


def test_the_new_page_form_shows_the_reason(setup):
    b, _page_id, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        login_met_sessie(page, session)
        page.goto("/admin/paginas/nieuw")
        pagina_klaar(page)
        line = page.locator("#pagina-nieuw-melding")
        empty = line.bounding_box()
        assert empty["height"] == 0, f"the empty message line takes room: {empty}"
        page.locator("#title").fill("Botsing")
        page.locator("#slug").fill("activiteiten")
        page.get_by_role("button", name="Opslaan").first.click()
        expect(line).to_contain_text(REASON)
        # The banner comes in with a transition: measure and print what is painted
        # once it ends, not the first frame (the master CLI's eye on the print).
        page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running')")
        box = line.bounding_box()
        painted = page.evaluate(
            """() => {
              const b = document.querySelector('#pagina-nieuw-melding [data-save-refusal]');
              const r = b.getBoundingClientRect();
              const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
              let opacity = 1;
              for (let e = b; e; e = e.parentElement) opacity *= +getComputedStyle(e).opacity;
              return {hit: b.contains(hit), opacity, visible: b.checkVisibility({opacityProperty: true}),
                      colour: getComputedStyle(b).color};
            }"""
        )
        print("MEASURE message line", empty, box, painted)
        assert painted["hit"] and painted["visible"] and painted["opacity"] == 1, painted
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390, "the message fits the phone"
        assert page.url.endswith("/admin/paginas/nieuw"), "no page was opened"
        _print(page, "nieuw-390.png")
    finally:
        page.close()
