"""E2E: on a phone, a family card's "Bewerken" stays inside the card (#1326).

Found while measuring CR-13 phase 3: in "Mijn gezin" at 390 px the "Bewerken"
button of the first family cards stuck out of the card on the right — 14 px for
the head of household, 2 px for the partner. The header row put the person's
details beside the button, and the details could not shrink below their longest
word: a long name, or an e-mail address, which has no place to break.

This test gives a household long names and long addresses, opens its portal at
390 and 1280 px, and measures every card: the right edge of "Bewerken" lies
within the card, and the page is exactly as wide as the viewport.

Proven red against master `75335a48` (29 September 2026): "@390: Bewerken sticks out
of 'Anne-Marie Vandenbroucke-Verhaegen' by 30 px"; 1280 px passed there too.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

LAST = "Vandenbroucke-Verhaegen"


@pytest.fixture(scope="module")
def household():
    """A head of household and a partner with long names and long addresses."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import ContactDetail, MemberPerson, Person
    from tests.conftest import create_test_family

    tag = secrets.token_hex(3)
    head_email = f"anne-marie.{LAST.lower()}.{tag}@example.com"
    db = SessionLocal()
    member, head = create_test_family(db, email=head_email)
    head.first_name, head.last_name = "Anne-Marie", LAST
    from datetime import date

    partner = Person(
        first_name="Jean-Baptiste", last_name=LAST, gender_code="M", date_of_birth=date(1981, 2, 3)
    )
    db.add(partner)
    db.flush()
    db.add(MemberPerson(member_id=member.id, person_id=partner.id, relation_type="PARTNER"))
    db.add(
        ContactDetail(
            person_id=partner.id,
            contact_type_code="EMAIL",
            value=f"jean-baptiste.{LAST.lower()}.{tag}@example.com",
            is_primary=True,
        )
    )
    db.commit()
    db.close()
    return head_email


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


_CARDS = """() => [...document.querySelectorAll('[x-data="{ edit: false }"]')]
  .filter(c => c.offsetParent !== null)
  .map(card => {
    const button = [...card.querySelectorAll('button')].find(b => b.innerText.trim() === 'Bewerken');
    const c = card.getBoundingClientRect();
    const b = button ? button.getBoundingClientRect() : null;
    return {
      name: (card.querySelector('.font-semibold') || {}).innerText,
      cardRight: Math.round(c.right), buttonRight: b ? Math.round(b.right) : null,
      doc: document.documentElement.scrollWidth, vw: innerWidth,
    };
  })"""


@pytest.mark.parametrize("width", [390, 1280])
def test_bewerken_stays_inside_every_card(browser, household, width):
    from app.domains.auth.api import make_session_value

    context = browser.new_context(base_url=BASE, viewport={"width": width, "height": 900})
    page = context.new_page()
    try:
        login_met_sessie(page, make_session_value(household))
        page.goto("/leden/gezin")
        pagina_klaar(page)
        cards = page.evaluate(_CARDS)
        assert len(cards) >= 2, f"@{width}: the household's cards are not on the page: {cards}"
        for card in cards:
            assert card["buttonRight"] is not None, f"@{width}: no Bewerken in {card}"
            assert card["buttonRight"] <= card["cardRight"], (
                f"@{width}: Bewerken sticks out of {card['name']!r} by "
                f"{card['buttonRight'] - card['cardRight']} px"
            )
        assert cards[0]["doc"] <= cards[0]["vw"], f"@{width}: page wider than the screen: {cards}"
    finally:
        context.close()
