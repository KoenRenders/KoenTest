"""E2E: Mijn inschrijvingen and what S5 changes around it (CR-22 S5, #1709; R8,
R27, Q39; Koen's answer of 7 October 2026 on the board's form).

- the page stands in the account layout; a registration's card is inside the
  content column, the transfer block inside the card, nothing wider than the
  window — at 390 and at 1 440 px;
- the landing page shows the latest registration as the same card;
- the hint above the public registration form carries the new words and stays
  one quiet block above the contact fields;
- **the board's form says to whom a registration will be linked** as soon as the
  typed address is a person's, before anything is saved, and takes it back when
  the address changes to nobody's.

A registration of the seeded member with a transfer still to make is made for
this file and removed again.

On master `2d98e19b` there is no route `/mijn/inschrijvingen`, the hint reads
"Lid van RAAK? Log je eerst aan: dan staat de inschrijving bij je gezin.", and
the board's form names nobody.
"""

import os
import sys
from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

OGM = "+++170/9000/00123+++"


@pytest.fixture(scope="module")
def world():
    """The seeded member's own registration for the seeded activity, with a
    booking of € 30 still to pay by transfer."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, Registration, RegistrationItem
    from app.domains.auth.api import login_person_for_email
    from app.domains.payment.api import PaymentRecord
    from seed_e2e import MARKER_EMAIL

    db = SessionLocal()
    try:
        person = login_person_for_email(db, MARKER_EMAIL)
        activity = db.query(Activity).filter(Activity.name == "E2E-activiteit").one()
        component = activity.sub_registrations[0]
        product = component.products[0]
        reg = Registration(
            activity_id=activity.id,
            component_id=component.id,
            person_id=person.id,
            registration_type="INDIVIDUAL",
            contact_name=f"{person.first_name} {person.last_name}",
            contact_email=MARKER_EMAIL,
            phone="0470 00 00 00",
        )
        db.add(reg)
        db.flush()
        item = RegistrationItem(registration_id=reg.id, product_id=product.id, quantity=3)
        booking = PaymentRecord(
            payable_type="registration",
            payable_id=reg.id,
            amount=Decimal("30.00"),
            method="transfer",
            status="pending",
            structured_communication=OGM,
        )
        db.add_all([item, booking])
        db.commit()
        made = {
            "reg": reg.id,
            "item": item.id,
            "booking": booking.id,
            "activity": activity.id,
            "component": component.id,
            "name": f"{person.first_name} {person.last_name}".strip(),
        }
    finally:
        db.close()

    yield made

    db = SessionLocal()
    try:
        for model, key in (
            (PaymentRecord, "booking"),
            (RegistrationItem, "item"),
            (Registration, "reg"),
        ):
            db.query(model).filter(model.id == made[key]).execution_options(
                include_all_tenants=True, include_deleted=True
            ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _as(browser, email: str, width: int, height: int):
    from app.domains.auth.api import make_session_value

    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    login_met_sessie(page, make_session_value(email), BASE)
    return page


CARD = (
    """(scope) => { const q = s => document.querySelector(s), r = e => e.getBoundingClientRect();
  const card = q(scope + ' [data-my-registration]'), content = q('[data-account-content]');
  const due = card.querySelector('[data-transfer-due]'), state = card.querySelector('[data-payment-state]');
  return {cards: document.querySelectorAll(scope + ' [data-my-registration]').length,
          card: [Math.round(r(card).left), Math.round(r(card).width)], content: [Math.round(r(content).left), Math.round(r(content).width)],
          due: due ? [Math.round(r(due).left - r(card).left), Math.round(r(card).right - r(due).right)] : null,
          title: card.querySelector('h2').textContent.trim(), amount: card.querySelector('[data-registration-amount]').textContent.trim(),
          state: [state.dataset.paymentState, state.textContent.trim()], lines: [...card.querySelectorAll('[data-registration-lines] li')].map(l => l.textContent.trim()),
          ogm: due ? due.textContent.includes('"""
    + OGM
    + """') : false,
          menu: q('[data-account-page-menu]').checkVisibility(), current: [...document.querySelectorAll('[data-account-page-menu] a[aria-current]')].map(a => a.getAttribute('href')),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""
)


@pytest.mark.parametrize(("width", "height", "menu"), [(390, 844, False), (1440, 900, True)])
def test_the_page_shows_the_registration_with_its_transfer(browser, world, width, height, menu):
    from seed_e2e import MARKER_EMAIL

    page = _as(browser, MARKER_EMAIL, width, height)
    page.goto("/mijn/inschrijvingen")
    pagina_klaar(page)
    m = page.evaluate(CARD, "[data-my-registrations]")
    print("MEASURE my registrations", width, m)
    assert m["cards"] >= 1 and m["title"] == "E2E-activiteit", m
    assert m["lines"] == ["3 × E2E-product"] and m["amount"] == "€ 30,00", m
    assert m["state"] == ["open", "Te betalen"], m["state"]
    # The card fills the content column; the transfer block stands inside it, 16 px from either edge.
    assert m["card"] == m["content"] and m["card"][1] <= 768, m
    assert m["due"] == [17, 17] and m["ogm"], m
    assert m["menu"] is menu and m["current"] == ["/mijn/inschrijvingen"], m
    assert m["page"][0] == m["page"][1]
    page.close()


def test_the_landing_page_shows_it_as_the_latest_registration(browser, world):
    from seed_e2e import MARKER_EMAIL

    page = _as(browser, MARKER_EMAIL, 390, 844)
    page.goto("/mijn")
    pagina_klaar(page)
    m = page.evaluate(CARD, "[data-latest-registration]")
    print("MEASURE latest registration 390", m)
    assert m["cards"] == 1 and m["title"] == "E2E-activiteit" and m["state"][0] == "open", m
    assert m["due"] == [17, 17] and m["ogm"] and m["card"] == m["content"], m
    assert (
        page.locator("[data-latest-registration] h2").first.inner_text().strip()
        == "Je laatste inschrijving"
    )
    page.locator('[data-latest-registration] a[href="/mijn/inschrijvingen"]').click()
    page.wait_for_url("**/mijn/inschrijvingen")
    page.close()


def test_the_hint_above_the_public_form_has_the_new_words(browser, world):
    page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    page.goto(f"/activiteiten/{world['activity']}/inschrijven/{world['component']}")
    pagina_klaar(page)
    m = page.evaluate(
        """() => { const n = document.querySelector('[data-member-nudge]'), r = n.getBoundingClientRect();
        const first = document.querySelector('input[name="contact_name"]').getBoundingClientRect();
        return {text: n.textContent.replace(/\\s+/g, ' ').trim(), h: Math.round(r.height), above: r.bottom <= first.top,
                link: n.querySelector('a').getAttribute('href'), page: [document.documentElement.scrollWidth, innerWidth]}; }"""
    )
    print("MEASURE hint 390", m)
    assert m["text"] == "Heb je een account of ben je lid? Log je eerst aan.", m["text"]
    assert m["above"] and m["link"].startswith("/aanmelden?terug=") and m["page"][0] == m["page"][1]
    page.close()


def test_the_boards_form_says_to_whom_the_registration_will_be_linked(browser, world):
    from seed_e2e import MARKER_EMAIL
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = _as(browser, os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL, 1440, 900)
    page.goto(
        f"/admin/activiteiten/{world['activity']}/inschrijvingen/nieuw?onderdeel={world['component']}"
    )
    pagina_klaar(page)
    link = page.locator("[data-registration-link]")
    assert link.count() == 1 and link.inner_text().strip() == "", (
        "the form names somebody before an address is typed"
    )
    email = page.locator('input[name="contact_email"]')
    email.fill(MARKER_EMAIL)
    email.blur()
    page.wait_for_function(
        "() => document.querySelector('[data-registration-link]').textContent.trim() !== ''"
    )
    assert link.inner_text().strip() == f"Deze inschrijving wordt gekoppeld aan {world['name']}."
    box = page.evaluate(
        """() => { const l = document.querySelector('[data-registration-link] p').getBoundingClientRect();
        const e = document.querySelector('input[name="contact_email"]').getBoundingClientRect();
        const p = document.querySelector('input[name="phone"]').getBoundingClientRect();
        return [l.top >= e.bottom, l.bottom <= p.top, document.documentElement.scrollWidth === innerWidth]; }"""
    )
    assert box == [True, True, True], (
        f"the notice does not stand between the address and the next field: {box}"
    )
    email.fill("niemand-1709@example.org")
    email.blur()
    page.wait_for_function(
        "() => document.querySelector('[data-registration-link]').textContent.trim() === ''"
    )
    page.close()
