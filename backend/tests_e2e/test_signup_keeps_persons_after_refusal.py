"""E2E: "Word lid" keeps every person after a refusal, and then registers them (#1327).

A family of three is typed in, sent with a postal code the server refuses, and the
page must come back with all three persons and what was typed. With the postal
code corrected, the same page registers the household with three persons.
Measured at 390 px, the phone width most visitors use.

Proven red against master `75335a48` (29 September 2026): after the refusal only
the head of household was on the page ("persons after the refusal: 1").
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, pagina_klaar  # noqa: E402

_ROWS = """() => [...document.querySelectorAll('input[name$="_first_name"]')].map(i => ({
  name: i.name, value: i.value,
  relation: (document.querySelector('select[name="' + i.name.replace('first_name', 'relation_type') + '"]') || {}).value || null,
})).concat([{doc: document.documentElement.scrollWidth, vw: innerWidth}])"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _person(page, n: int, first: str, last: str) -> None:
    page.fill(f"#m{n}_first_name", first)
    page.fill(f"#m{n}_last_name", last)
    page.fill(f"#m{n}_date_of_birth", "2001-02-03")
    page.select_option(f"#m{n}_gender_code", "M")


def _household_size(last_name: str) -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import Person

    db = SessionLocal()
    try:
        head = db.query(Person).filter_by(last_name=last_name, first_name="Hoofd").one()
        return len(head.member_persons[0].member.member_persons)
    finally:
        db.close()


def test_a_refusal_keeps_three_persons_and_a_correction_registers_them(browser):
    last = f"Terugkeer{secrets.token_hex(2)}"
    context = browser.new_context(base_url=BASE, viewport={"width": 390, "height": 900})
    page = context.new_page()
    try:
        page.goto("/lid-worden")
        pagina_klaar(page)
        _person(page, 0, "Hoofd", last)
        page.fill("#m0_email", f"{last.lower()}@example.com")
        page.fill("#m0_mobile", "0470000000")
        for _ in range(2):
            page.get_by_role("button", name="+ Gezinslid toevoegen").click()
            htmx_stil(page)
        _person(page, 1, "Pieter", last)
        _person(page, 2, "Lotte", last)
        page.fill("#street", "Teststraat")
        page.fill("#house_number", "1")
        page.check('input[name="payment_method"][value="transfer"]')
        # A postal code the server does not know: the refusal under test.
        page.evaluate("""() => { const s = document.querySelector('#postal_code');
            s.add(new Option('9999 Nergens', '9999')); s.value = '9999'; }""")
        page.get_by_role("button", name="Word lid").click()
        htmx_stil(page)
        pagina_klaar(page)

        rows = page.evaluate(_ROWS)
        width = rows.pop()
        persons = [r for r in rows if r["value"]]
        assert len(persons) == 3, f"persons after the refusal: {len(persons)} — {rows}"
        assert [p["value"] for p in persons] == ["Hoofd", "Pieter", "Lotte"], rows
        assert [p["relation"] for p in persons[1:]] == ["PARTNER", "KIND"], rows
        assert width["doc"] <= width["vw"], width

        page.select_option("#postal_code", index=1)
        page.get_by_role("button", name="Word lid").click()
        page.wait_for_load_state()
        htmx_stil(page)
        assert _household_size(last) == 3
    finally:
        context.close()
