"""E2E #1831 — the Leden screen says why it refuses, in the card that was saved.

A household's page has a form per card. A refusal of one answered a bare JSON
error, and the page showed the kit's general message. The route tests
(`mdm/tests/test_household_cards_say_why_1831.py`) hold that the answer is the kit's
refusal for the card's own message line; this file holds what only a browser
can: that the sentence is **on the screen, in that card, in view**, after what
the browser itself lets through.

What the browser lets through: a required text field of spaces (`required` is
satisfied by a space), and an e-mail address that is well formed but belongs to
someone else. An empty required field, a date that is none and a relation
outside the list never leave a browser — those are the route tests'.

Everything is measured at 390 px, the width most visitors have: the banner
stands inside its card, inside the viewport without scrolling from the button
that was pressed, and the page does not scroll sideways.

Set `E2E_PRINTS` to a folder to keep a print of each refusal (outside the
repository: prints never go in).

Proven red (locally, restored): the decorator `says_why_in` taken off
`adres_opslaan` → the address test fails on the banner that never comes; the
add card's message line put back at the head of the card → its test fails on
"the banner is out of view".
"""

from __future__ import annotations

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

RUN = secrets.token_hex(3)
TAKEN = f"bezet-{RUN}@example.com"
ADDRESS_RULE = "Een adres heeft een straat, een huisnummer en een postcode nodig."
NAME_RULE = "Voornaam en achternaam zijn verplicht."
IN_USE = "Dit e-mailadres is al in gebruik door iemand anders."

_GEOMETRY = """([line, card]) => {
  const banner = document.querySelector(line + ' [data-save-refusal]').getBoundingClientRect();
  const box = document.querySelector(card).getBoundingClientRect();
  return {
    inside: banner.left >= box.left - 0.5 && banner.right <= box.right + 0.5
            && banner.top >= box.top - 0.5 && banner.bottom <= box.bottom + 0.5,
    in_view: banner.top >= 0 && banner.bottom <= window.innerHeight,
    sideways: document.documentElement.scrollWidth - window.innerWidth,
  };
}"""


@pytest.fixture(scope="module")
def page():
    from app.domains.auth.api import csrf_token_for, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    session = make_session_value(email)
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
        login_met_sessie(page, session)
        page.csrf = csrf_token_for(session)  # type: ignore[attr-defined]
        yield page
        browser.close()


def _new_household(page, first: str, email: str, *, partner: bool) -> int:
    """A household made through the door the screen uses; its id."""
    page.goto("/admin/leden/nieuw")
    pagina_klaar(page)
    postal_code = page.eval_on_selector(
        "#postal_code", "el => [...el.options].map(o => o.value).filter(Boolean)[0]"
    )
    form = {
        "street": "Proefstraat",
        "house_number": "12",
        "bus_number": "",
        "postal_code": postal_code,
        "m0_first_name": first,
        "m0_last_name": f"Proef-{RUN}",
        "m0_date_of_birth": "1980-03-04",
        "m0_gender_code": "F",
        "m0_email": email,
        "m0_phone": "",
        "m0_mobile": "0470 00 00 01",
    }
    if partner:
        form |= {
            "m1_first_name": "Bram",
            "m1_last_name": f"Proef-{RUN}",
            "m1_date_of_birth": "1979-05-06",
            "m1_gender_code": "M",
            "m1_email": "",
            "m1_phone": "",
            "m1_mobile": "",
        }
    answer = page.request.post(
        "/admin/leden", form=form, headers={"X-CSRF-Token": page.csrf, "HX-Request": "true"}
    )
    assert answer.status == 204, (answer.status, answer.text()[:300])
    return int(answer.headers["hx-redirect"].rsplit("/", 1)[-1])


@pytest.fixture(scope="module")
def household(page) -> int:
    """A household of a main member and a partner — and, apart from it, a person
    who holds the address the add card will ask for."""
    _new_household(page, "Buiten", TAKEN, partner=False)
    return _new_household(page, "Hanne", f"hanne-{RUN}@example.com", partner=True)


def _open(page, household: int) -> None:
    page.goto(f"/admin/leden/gezin/{household}")
    pagina_klaar(page)


def _sideways(page) -> int:
    """How far the page scrolls sideways, in px (0 or less: not at all)."""
    return page.evaluate("document.documentElement.scrollWidth - window.innerWidth")


def _measure(page, line: str, card: str, sentence: str, name: str, before: int) -> None:
    """`before`: the sideways scroll with the card open, before the refusal."""
    banner = page.locator(f"{line} [data-save-refusal]")
    expect(banner).to_be_visible(timeout=10_000)
    expect(banner).to_contain_text("Opslaan is niet gelukt.")
    expect(banner).to_contain_text(sentence)
    measured = page.evaluate(_GEOMETRY, [line, card])
    prints = os.environ.get("E2E_PRINTS")
    if prints:
        page.screenshot(path=os.path.join(prints, f"{name}-390.png"))
    assert measured["inside"], f"the banner stands outside its card: {measured}"
    assert measured["in_view"], (
        f"the banner is out of view after the button was pressed: {measured}"
    )
    # No sideways scroll, with the card open before the refusal and after it. The
    # open card of a person was 76 px wider than the page at 390 px until #1831:
    # whoever scrolled to Opslaan lost the start of the sentence.
    print(f"SIDEWAYS {name}: {before} px before the refusal, {measured['sideways']} px after")
    assert before <= 0, f"the open card is {before} px wider than the page"
    assert measured["sideways"] <= 0, f"the page scrolls sideways by {measured['sideways']} px"


def test_the_address_card_says_why(page, household):
    _open(page, household)
    card = page.locator("#adres-kaart")
    card.get_by_role("button", name="Bewerken").click()
    card.locator("#street").fill("   ")
    before = _sideways(page)

    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/adres")
    ) as answered:
        card.get_by_role("button", name="Opslaan").click()

    assert answered.value.status == 422
    _measure(page, "#adres-melding", "#adres-kaart", ADDRESS_RULE, "adres", before)
    # What was typed is still there: the answer is the banner alone.
    assert card.locator("#house_number").input_value() == "12"


def _partner_card(page):
    return page.locator('[id^="persoon-"]:not([id$="-melding"]):not(#persoon-toevoegen)').filter(
        has_text="Bram"
    )


def test_a_persons_card_says_why_and_leaves_the_other_cards_alone(page, household):
    _open(page, household)
    # An unsaved change in ANOTHER card: it must survive this card's refusal.
    address = page.locator("#adres-kaart")
    address.get_by_role("button", name="Bewerken").click()
    address.locator("#street").fill("Nog niet bewaard")

    card = _partner_card(page)
    card_id = card.get_attribute("id")
    card.get_by_role("button", name="Bewerken").click()
    card.locator('input[name="first_name"]').fill("   ")
    before = _sideways(page)

    with page.expect_response(
        lambda r: r.request.method == "POST" and "/persoon/" in r.url
    ) as answered:
        card.get_by_role("button", name="Opslaan").click()

    assert answered.value.status == 422
    _measure(page, f"#{card_id}-melding", f"#{card_id}", NAME_RULE, "persoon", before)
    assert address.locator("#street").input_value() == "Nog niet bewaard", (
        "a refusal in one card threw away what was typed in another"
    )
    assert page.locator("#adres-melding [data-save-refusal]").count() == 0, (
        "the sentence landed in another card's line too"
    )


def test_a_good_save_after_a_refusal_empties_the_line(page, household):
    _open(page, household)
    card = _partner_card(page)
    card_id = card.get_attribute("id")
    card.get_by_role("button", name="Bewerken").click()
    name = card.locator('input[name="first_name"]')
    name.fill("   ")
    with page.expect_response(lambda r: r.request.method == "POST" and "/persoon/" in r.url):
        card.get_by_role("button", name="Opslaan").click()
    expect(page.locator(f"#{card_id}-melding [data-save-refusal]")).to_be_visible()

    name.fill("Bram")
    with page.expect_response(
        lambda r: r.request.method == "POST" and "/persoon/" in r.url
    ) as answered:
        card.get_by_role("button", name="Opslaan").click()

    assert answered.value.status == 200
    expect(page.locator(f"#{card_id}-melding [data-save-refusal]")).to_have_count(0)


def test_the_add_card_says_why_by_its_button(page, household):
    _open(page, household)
    card = page.locator("#persoon-toevoegen")
    card.get_by_role("button", name="+ Persoon toevoegen").click()
    card.locator('input[name="first_name"]').fill("Extra")
    card.locator('input[name="last_name"]').fill(f"Proef-{RUN}")
    card.locator('input[name="date_of_birth"]').fill("2010-07-08")
    card.locator('select[name="gender_code"]').select_option("F")
    card.locator('input[name="email"]').fill(TAKEN)
    before = _sideways(page)

    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/personen")
    ) as answered:
        card.get_by_role("button", name="Toevoegen", exact=True).click()

    assert answered.value.status == 422
    _measure(page, "#persoon-toevoegen-melding", "#persoon-toevoegen", IN_USE, "toevoegen", before)
    assert card.locator('input[name="first_name"]').input_value() == "Extra"


_BUTTONS = """(card) => {
  const box = document.querySelector(card).getBoundingClientRect();
  const rects = [...document.querySelectorAll(card + ' button')]
    .filter(b => b.checkVisibility() && ['Verwijderen', 'Annuleren', 'Opslaan'].includes(b.textContent.trim()))
    .map(b => ({name: b.textContent.trim(), ...b.getBoundingClientRect().toJSON()}));
  const title = [...document.querySelectorAll(card + ' span')].find(s => s.checkVisibility() && s.textContent.includes('bewerken'));
  return {
    rows: new Set(rects.map(r => Math.round(r.top))).size,
    names: rects.map(r => r.name),
    inside: rects.every(r => r.left >= box.left - 0.5 && r.right <= box.right + 0.5),
    beside_title: title ? Math.abs(title.getBoundingClientRect().top - rects[0].top) < 30 : null,
    sideways: document.documentElement.scrollWidth - window.innerWidth,
  };
}"""


@pytest.mark.parametrize(("width", "one_row"), [(390, False), (1100, True)])
def test_the_buttons_of_a_persons_card_stay_inside_it(page, household, width, one_row):
    """Narrow: the three buttons of the edit state wrap, inside the card, and the
    page does not scroll sideways. Wide: one row, beside the title, as it was."""
    page.set_viewport_size({"width": width, "height": 844})
    try:
        _open(page, household)
        card = _partner_card(page)
        card_id = card.get_attribute("id")
        card.get_by_role("button", name="Bewerken").click()
        expect(card.get_by_role("button", name="Opslaan")).to_be_visible()
        measured = page.evaluate(_BUTTONS, f"#{card_id}")
        prints = os.environ.get("E2E_PRINTS")
        if prints:
            page.screenshot(path=os.path.join(prints, f"persoon-bewerken-{width}.png"))
    finally:
        page.set_viewport_size({"width": 390, "height": 844})

    print(f"BUTTONS at {width} px: {measured}")
    assert measured["names"] == ["Verwijderen", "Annuleren", "Opslaan"], measured
    assert measured["inside"], f"a button stands outside the card: {measured}"
    assert measured["sideways"] <= 0, f"the page scrolls sideways by {measured['sideways']} px"
    assert (measured["rows"] == 1) is one_row, measured
    if one_row:
        assert measured["beside_title"], f"the buttons left the title's row: {measured}"
