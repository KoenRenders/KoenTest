"""E2E: an e-mail address typed in Mijn gegevens waits for its code (CR-22 S6b, #1711; R15).

The round a person makes, on a phone:

- he adds an address and saves: the page comes back in read mode and the new
  row says "wacht op bevestiging", with "Code invoeren" and "Code opnieuw
  sturen" under the address — inside the card, each a finger high, the page no
  wider than the window;
- "Code opnieuw sturen" leads to the page that asks the code, which names the
  address;
- the code makes the address count: back on Mijn gegevens, the row has lost
  its mark, and he is still signed in as himself.

The address is added to the seeded member and taken away again.

On master `da1cfe67` a typed address counted at once: no mark, no code page.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

ADDRESS = "wacht-1711@example.org"
CODE = "424242"


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
    from app.domains.mdm.api import ContactDetail
    from app.soft_delete import soft_delete

    db = SessionLocal()
    try:
        for contact in db.query(ContactDetail).filter(ContactDetail.value == email).all():
            soft_delete(contact)
        db.commit()
    finally:
        db.close()


WAITING = """() => { const r = e => e.getBoundingClientRect(), n = v => Math.round(v);
  const line = document.querySelector('[data-email-waiting]');
  if (!line) return null;
  const row = line.closest('[data-group-row]'), card = document.querySelector('[data-my-details]');
  const value = row.querySelector('[data-value]');
  const actions = [line.querySelector('[data-enter-code]'), line.querySelector('[data-send-code]')];
  return {address: value.textContent.trim(), badge: line.querySelector('[data-badge]').textContent.trim(),
          actions: actions.map(a => a.textContent.trim()), heights: actions.map(a => n(r(a).height)),
          under: r(line).top >= r(value).bottom - 0.5,
          inside: r(line).left >= r(card).left && actions.every(a => r(a).right <= r(card).right + 0.5),
          line: [n(r(line).left), n(r(line).top), n(r(line).width), n(r(line).height)],
          card: [n(r(card).left), n(r(card).width)],
          primary_tags: [...document.querySelectorAll('[data-row-one-tag]')].filter(t => t.checkVisibility()).length,
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


EDIT = """() => { const r = e => e.getBoundingClientRect();
  const tag = document.querySelector('[data-main-emails] [data-row-tag]');
  if (!tag) return null;
  const row = tag.closest('[data-group-row]'), input = row.querySelector('input[type=email]');
  const a = r(tag), b = r(input);
  return {tag: tag.textContent.trim(), value: input.value,
          clear: a.bottom <= b.top + 0.5 || a.left >= b.right - 0.5,
          menu: [...row.querySelectorAll('[data-row-action]')].map(i => i.dataset.rowAction),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


def _save(page) -> None:
    page.locator(
        '[data-action-bar] button[type="submit"], [data-action-bar] button[form="gegevens-form"]'
    ).first.click()
    page.wait_for_function(
        "() => document.querySelector('[data-form-flow]').dataset.mode === 'read'"
    )
    pagina_klaar(page)


def test_a_typed_address_waits_and_its_code_makes_it_count(browser):
    from app.domains.auth.api import make_session_value
    from seed_e2e import MARKER_EMAIL

    _remove(ADDRESS)
    page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    login_met_sessie(page, make_session_value(MARKER_EMAIL), BASE)
    try:
        page.goto("/mijn/gegevens?bewerken=1")
        pagina_klaar(page)
        page.locator("[data-main-emails] [data-group-add]").first.click()
        page.locator('[data-main-emails] input[type="email"]').last.fill(ADDRESS)
        _save(page)

        waiting = page.evaluate(WAITING)
        print("MEASURE waiting address 390", waiting)
        assert waiting, "the new address shows no waiting mark"
        assert waiting["address"] == ADDRESS and waiting["badge"] == "wacht op bevestiging"
        assert waiting["actions"] == ["Code invoeren", "Code opnieuw sturen"], waiting
        assert min(waiting["heights"]) >= 44, waiting["heights"]
        assert waiting["under"] and waiting["inside"], waiting
        # The address he had is still the primary one — the only one marked so.
        assert waiting["primary_tags"] == 1, waiting
        assert waiting["page"][0] == waiting["page"][1], waiting

        # While editing, the mark stands where another row carries "hoofdadres",
        # and the row's menu does not offer to make it the primary address.
        page.goto("/mijn/gegevens?bewerken=1")
        pagina_klaar(page)
        edit = page.evaluate(EDIT)
        print("MEASURE waiting address edit 390", edit)
        assert edit["tag"] == "wacht op bevestiging" and edit["clear"], edit
        assert edit["menu"] == ["remove"], edit
        assert edit["page"][0] == edit["page"][1], edit
        page.goto("/mijn/gegevens")
        pagina_klaar(page)

        page.locator("[data-send-code]").click()
        page.wait_for_url("**/bevestigen?terug=/mijn/gegevens")
        pagina_klaar(page)
        assert ADDRESS in page.locator("[data-confirm-address]").inner_text()
        step = page.evaluate(
            "() => ({title: document.querySelector('#main h1').textContent.trim(),"
            " button: document.querySelector('#aanmelden-stap button').textContent.trim(),"
            " page: [document.documentElement.scrollWidth, innerWidth]})"
        )
        print("MEASURE confirm address page 390", step)
        assert step["title"] == "Bevestig je e-mailadres" and step["button"] == "Bevestigen", step
        assert step["page"][0] == step["page"][1], step

        _set_code(ADDRESS)
        page.fill("#code", CODE)
        page.locator("#aanmelden-stap button").click()
        page.wait_for_url("**/mijn/gegevens")
        pagina_klaar(page)
        assert page.evaluate(WAITING) is None, "the confirmed address still says it waits"
        details = page.locator("[data-my-details]").inner_text()
        assert ADDRESS in details and MARKER_EMAIL in details
    finally:
        page.close()
        _remove(ADDRESS)
