"""E2E: the circle search shows each person's address, and a long one fits (#1353).

Two namesakes, one with a long address, and a third person without one. At 390
and 1280 px the search results of "Iemand toevoegen" show the address beside the
right name, "geen e-mailadres" for the third, and the long address wraps inside
the row: the "Toevoegen" button stays inside the card and the page does not grow.
"""

import os
import secrets
import sys
from datetime import date

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_als_admin  # noqa: E402

SHOTS = "/scratch/shots_1353"
LONG = "lieve.met.een.heel.lang.adres@een-voorbeeld-van-een-lang-domein.example"

_MEASURE = """() => {
  const rows = [...document.querySelectorAll('#vg-kring-kandidaten form')];
  const card = document.querySelector('#vg-kring-kandidaten').closest('.rounded-2xl');
  return {
    doc: document.documentElement.scrollWidth, vw: innerWidth,
    card_right: Math.round(card.getBoundingClientRect().right),
    rows: rows.map(r => ({
      text: r.innerText.replace(/\\s+/g, ' ').trim(),
      button_right: Math.round(r.querySelector('button').getBoundingClientRect().right),
      widest: Math.max(...[...r.querySelectorAll('*')].map(e => e.getBoundingClientRect().right)),
    })),
  };
}"""


def _people(last: str) -> None:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import ContactDetail, Person

    db = SessionLocal()
    try:
        for first, email in (("Lieve", "lieve.kort@example.org"), ("Lieve", LONG), ("Lies", None)):
            person = Person(first_name=first, last_name=last, date_of_birth=date(1980, 1, 1))
            db.add(person)
            db.flush()
            if email:
                db.add(
                    ContactDetail(
                        person_id=person.id,
                        contact_type_code="EMAIL",
                        value=email,
                        is_primary=True,
                    )
                )
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, email, make_session_value(email)
        b.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_the_results_show_the_address_and_fit(browser, width):
    last = f"Naamgenoot{secrets.token_hex(2)}"
    _people(last)
    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto("/admin/vergaderingen/kring")
        htmx_stil(page)
        page.fill("input[name=q]", last)
        expect(page.locator("#vg-kring-kandidaten form")).to_have_count(3)

        m = page.evaluate(_MEASURE)
        print(f"MEASURE @{width}", m)
        texts = [r["text"] for r in m["rows"]]
        assert any("lieve.kort@example.org" in t for t in texts), texts
        assert any(LONG in t for t in texts), texts
        assert any(t.startswith(f"Lies {last}") and "geen e-mailadres" in t for t in texts), texts
        assert m["doc"] <= m["vw"], f"@{width}: the page is {m['doc']} px wide"
        for row in m["rows"]:
            assert row["button_right"] <= m["card_right"], row
            assert row["widest"] <= m["card_right"], row

        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.locator("#vg-kring-kandidaten").scroll_into_view_if_needed()
            page.wait_for_function(
                "() => document.getAnimations().every(a => a.playState !== 'running')"
            )
            page.screenshot(path=f"{SHOTS}/{width}-zoekresultaten.png")
    finally:
        page.close()
