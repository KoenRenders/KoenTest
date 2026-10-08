"""E2E: making an account in the browser (CR-22 S4b, #1708; AC1, W1).

- from the sign-in screen the link "Account aanmaken" opens the form; at 390
  and at 1440 px the four fields stand inside the card, equally high, nothing
  wider than the window;
- sending it empty puts each refusal under its own field and keeps the form;
  what was typed stays;
- a good request is answered in place by the code step — "We stuurden een code
  naar dit adres.", the button "Bevestigen" — and the right code signs in and
  lands on the account page, where the new name stands.

The code is read from the test's own token (the hash of a code the test sets);
the person made is deleted again.

On master there is no route `/account-aanmaken`.
"""

import os
import sys
import uuid

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, pagina_klaar  # noqa: E402

CODE = "135790"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _set_code(email: str) -> None:
    """The server made a code this test cannot read (only its hash is kept):
    put the hash of a known one on the living token of this address."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth import login
    from app.domains.auth.api import LoginToken

    db = SessionLocal()
    try:
        token = db.query(LoginToken).filter_by(email=email, used=False).one()
        token.otp_code = login._hash_otp(CODE)
        db.commit()
    finally:
        db.close()


def _remove(email: str) -> None:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import ContactDetail, Person
    from app.soft_delete import soft_delete

    db = SessionLocal()
    try:
        for contact in db.query(ContactDetail).filter(ContactDetail.value == email).all():
            person = db.query(Person).filter(Person.id == contact.person_id).first()
            if person is not None:
                for other in person.contact_details:
                    soft_delete(other)
                soft_delete(person)
        db.commit()
    finally:
        db.close()


SHAPE = """() => { const q = s => document.querySelector(s), all = s => [...document.querySelectorAll(s)];
  const card = q('[data-sign-in-step]').parentElement.getBoundingClientRect();
  const inputs = all('[data-sign-in-step] input:not([type=hidden])');
  return {title: q('#main h1').innerText.trim(), names: inputs.map(i => i.name),
          heights: [...new Set(inputs.map(i => Math.round(i.getBoundingClientRect().height)))],
          inside: inputs.every(i => { const b = i.getBoundingClientRect(); return b.left >= card.left && b.right <= card.right; }),
          invalid: all('[data-sign-in-step] [aria-invalid=true]').map(i => i.name),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


# The form is SENT at the phone width only: the route is limited to five sends
# a minute per IP (`login_limiter`) and this walk is three of them.
@pytest.mark.parametrize(("width", "height", "send"), [(390, 844, True), (1440, 900, False)])
def test_from_the_sign_in_screen_to_an_account(browser, width, height, send):
    email = f"proef-{uuid.uuid4().hex[:8]}@example.org"
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    try:
        page.goto("/aanmelden?terug=/mijn/gegevens")
        pagina_klaar(page)
        # A full load of the link's address: a boosted swap keeps the old
        # page's attributes on an element with the same id for a moment.
        href = page.locator("[data-create-account] a").get_attribute("href")
        assert href == "/account-aanmaken?terug=/mijn/gegevens", href
        page.goto(href)
        pagina_klaar(page)
        shape = page.evaluate(SHAPE)
        print("MEASURE create account", width, shape)
        assert shape["title"] == "Account aanmaken"
        assert shape["names"] == ["first_name", "last_name", "email", "mobile"], shape
        assert len(shape["heights"]) == 1 and shape["inside"], shape
        assert shape["page"][0] == shape["page"][1], "wider than the window"
        if not send:
            return

        form = page.locator("[data-create-account-form]")
        form.locator('input[name="last_name"]').fill("Proefpersoon")
        with htmx_afgerond(page):
            form.locator("button").click()
        refused = page.evaluate(SHAPE)
        assert refused["invalid"] == ["first_name", "email", "mobile"], refused
        expect(page.locator('[data-field="first_name"]')).to_contain_text("Vul je voornaam in.")
        expect(page.locator('[data-field="email"]')).to_contain_text(
            "Vul een geldig e-mailadres in."
        )
        expect(page.locator('input[name="last_name"]')).to_have_value("Proefpersoon")
        assert refused["page"][0] == refused["page"][1]

        form = page.locator("[data-create-account-form]")
        form.locator('input[name="first_name"]').fill("Petra")
        form.locator('input[name="email"]').fill(email)
        form.locator('input[name="mobile"]').fill("0470 00 17 08")
        with htmx_afgerond(page):
            form.locator("button").click()
        expect(page.locator("[data-code-sent]")).to_have_text(
            "We stuurden een code naar dit adres."
        )
        expect(page.locator("[data-sign-in-step] button")).to_have_text("Bevestigen")
        expect(page.locator("[data-create-account-form]")).to_have_count(0)

        _set_code(email)
        page.locator('input[name="code"]').fill(CODE)
        page.locator("[data-sign-in-step] button").click()
        # The page that asked wins over the landing (#1437): Mijn gegevens.
        # By the path, not a glob: this page's own address ends in the same words.
        page.wait_for_url(lambda url: url.split("?")[0].endswith("/mijn/gegevens"))
        pagina_klaar(page)
        expect(page.locator("#main")).to_contain_text("Petra")
        expect(page.locator("#main")).to_contain_text("Proefpersoon")
    finally:
        page.close()
        _remove(email)


CARD = """() => { const q = s => document.querySelector(s);
  const box = e => { const b = e.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.width)]; };
  const input = q('[data-sign-in-step] input:not([type=hidden])');
  return {card: box(q('[data-sign-in-card]')), field: box(input), main: box(q('[data-main]')),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize(("width", "card"), [(1440, 768), (1920, 768), (390, 358)])
def test_the_two_sign_in_screens_share_one_narrow_card(browser, width, card):
    """#1730 (Koen, 8 October 2026: "smaller is goed"): one card for Inloggen
    and Account aanmaken — 768 px since #1737 (448 px in #1730), centred, the same on both; on a phone the
    width it had.

    Red: the wrapper taken out of `_sign_in_card.html` → the card is 1 248 px
    at 1 440 and its field 1 198."""
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        found = {}
        for path in ("/aanmelden", "/account-aanmaken"):
            page.goto(path)
            pagina_klaar(page)
            found[path] = page.evaluate(CARD)
        print("MEASURE sign-in card", width, found)
        sign_in, create = found["/aanmelden"], found["/account-aanmaken"]
        assert sign_in["card"] == create["card"], "the two screens differ in their card"
        assert sign_in["field"] == create["field"], "the two screens differ in their field"
        assert sign_in["card"][1] == card, sign_in
        assert sign_in["field"][1] == card - 50, (
            "the field is not the card less its padding and border"
        )
        centre = sign_in["card"][0] + sign_in["card"][1] / 2
        assert abs(centre - width / 2) <= 1, f"the card is not centred: {centre} of {width}"
        assert sign_in["page"][0] == sign_in["page"][1]
    finally:
        page.close()
