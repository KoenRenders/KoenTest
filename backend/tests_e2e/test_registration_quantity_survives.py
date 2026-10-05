"""E2E: a quantity that is typed is never overwritten by an answer that lands
late (#1596).

Measured on master before the repair (4 and 5 October 2026):

- **the board's page**: changing the e-mail address asked the price block
  again, and the answer WAS the block — rows, quantity fields and total, with
  the quantities of the moment the request left. An answer that landed after
  the board member had typed a quantity put it back: 8 became 1, and the
  registration was saved with 1, without a word. And because htmx returns the
  focus to the field of the same id after a swap, digits typed WHILE the answer
  landed went into the new field before its opening "1": 8 became 81 — refused
  with a maximum of 50, accepted without one;
- **the public page** has no such refresh, and no field of it was ever
  swapped. What it shared with the board: two changes in two quantity fields
  sent two requests for the total, and the one that arrived last won — also
  when it was the older one. The total on screen then no longer belonged to
  the fields (the amount charged was always right: the server computes it again
  at the submit).

The repair: an answer carries what the server DERIVES (the total, the price of
a row) and never a field; and the requests of the price block share one queue
in which the newest replaces the one under way.

Each test holds an answer back in the browser and lets it go when it chooses —
the order of arrival is the test's, not the network's — and reads the saved
registration in a session of its own.

Proven red against master `debd9a4f` (the three tests, each on its own):
- the late price answer: the field read "1" (the typed 8 was put back) and the
  registration was saved with 1;
- typing while the answer lands: the field read "81";
- two changes, the older answer last: the total read "€10,00" beside fields
  that made € 40,00.
"""

import os
import secrets
import sys
from decimal import Decimal

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def setup():
    """An activity with two paid products (10 and 30 euro), and a board member."""
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.activities.api import ActivityProduct
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole
    from tests.conftest import seed_activity_with_product

    db = SessionLocal()
    activity, component, first = seed_activity_with_product(db, price="10.00", is_free=False)
    second = ActivityProduct(
        component_id=component.id, name="Tweede product", price=Decimal("30.00"), is_free=False
    )
    db.add(second)
    email = f"e2e-1596-{secrets.token_hex(3)}@example.org"
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()
    out = {
        "activity": activity.id,
        "public": f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        "board": f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw",
        "first": first.id,
        "second": second.id,
        "session": make_session_value(email),
    }
    db.close()
    return out


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


class Held:
    """Answers the browser asked for and has not been given yet. The request
    goes to the server at once; its answer waits here until `release`."""

    def __init__(self, page, suffix: str):
        self.waiting: list = []
        self.page = page
        page.route(f"**/*{suffix}", self._hold)

    def _hold(self, route) -> None:
        if route.request.method != "POST" or self.closed:
            route.continue_()
            return
        response = route.fetch()
        if self.closed:
            # `stop` ran while this answer was being fetched: nothing holds it.
            self._answer(route, response)
            return
        self.waiting.append((route, response))

    closed = False

    def expect(self, count: int) -> None:
        for _ in range(100):
            if len(self.waiting) >= count:
                return
            self.page.evaluate("() => new Promise(r => requestAnimationFrame(r))")
        raise AssertionError(f"{len(self.waiting)} answer(s) held, expected {count}")

    @staticmethod
    def _answer(route, response) -> None:
        try:
            route.fulfill(response=response)
        except Exception:
            pass  # the page aborted this request meanwhile: nothing to answer

    def release(self, index: int = 0) -> None:
        self._answer(*self.waiting.pop(index))

    def stop(self) -> None:
        self.closed = True
        while self.waiting:
            self.release()


def _saved(activity_id: int, name: str) -> dict[int, int]:
    """product id → quantity of the registration saved under this name, read in
    a session of our own."""
    from app.database import SessionLocal
    from app.domains.activities.api import Registration

    db = SessionLocal()
    try:
        registration = (
            db.query(Registration)
            .filter(Registration.activity_id == activity_id, Registration.contact_name == name)
            .one()
        )
        return {item.product_id: item.quantity for item in registration.items}
    finally:
        db.close()


def _board(browser, setup):
    page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    login_met_sessie(page, setup["session"])
    page.goto(setup["board"])
    pagina_klaar(page)
    page.wait_for_function("() => !!window.raakRecordForm && window.raakRecordForm.ready()")
    return page


def test_a_late_price_answer_leaves_the_typed_quantity(browser, setup):
    page = _board(browser, setup)
    name = f"Laat Antwoord {secrets.token_hex(2)}"
    quantity = page.locator(f"#product-{setup['first']}")
    held = Held(page, "/nieuw/prijzen")

    page.fill("#contact_name", name)
    page.fill("#contact_email", "laat-antwoord@example.org")
    page.fill("#phone", "0470000000")  # the address loses the focus: the prices are asked
    held.expect(1)
    quantity.fill("8")  # typed while that answer is under way
    held.stop()  # every answer still waiting lands now, late
    htmx_stil(page)

    assert quantity.input_value() == "8", "the late answer put the typed quantity back"
    expect(page.locator("[data-total]")).to_contain_text("80,00")
    page.locator('input[name="payment_method"][value="transfer"]').check()
    page.click("[data-form-save]")
    page.wait_for_url("**/admin/inschrijvingen/*")
    assert _saved(setup["activity"], name) == {setup["first"]: 8}
    page.close()


def test_digits_typed_while_the_answer_lands_are_not_mangled(browser, setup):
    """The "81": the swap took the field away under the typist and htmx put the
    focus on its successor. With no field in the answer there is nothing to
    land in."""
    page = _board(browser, setup)
    quantity = page.locator(f"#product-{setup['first']}")
    held = Held(page, "/nieuw/prijzen")

    page.fill("#contact_email", "tijdens-het-typen@example.org")
    quantity.select_text()  # what `fill` does first …
    held.expect(1)
    held.stop()  # … the answer lands between the select and the insert …
    htmx_stil(page)
    page.keyboard.insert_text("8")  # … and the digit arrives after it
    htmx_stil(page)

    assert quantity.input_value() == "8", "the digit landed in a field the answer brought"
    assert page.evaluate("() => document.activeElement.id") == f"product-{setup['first']}"
    page.close()


def test_the_total_is_the_answer_to_the_fields_also_when_an_older_answer_is_last(browser, setup):
    """The public page: two changes in two fields. The first answer is held
    back and let go after the second: it may not win."""
    page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    page.goto(setup["public"])
    pagina_klaar(page)
    page.wait_for_function("() => !!window.raakRecordForm && window.raakRecordForm.ready()")
    name = f"Twee Wijzigingen {secrets.token_hex(2)}"
    first = page.locator(f"#product-{setup['first']}")
    second = page.locator(f"#product-{setup['second']}")
    total = page.locator("[data-total]")
    held = Held(page, "/totaal")

    # The counter's own "+": one `change` per click and nothing after it — a
    # typed digit also fires when the field loses the focus, and that third
    # request would repair on its own what this test is about.
    plus = page.locator("[data-product-row] button[aria-label^='Eén meer']")
    plus.nth(0).click()
    held.expect(1)  # the answer for "1 and 0" (€ 10) waits
    plus.nth(1).click()
    # Both answers are held now: the browser may have given the older request
    # up, but its answer still waits here to be let go.
    held.expect(2)
    # Let the NEWEST go first and the oldest last — the order that used to lose.
    held.release(1)
    expect(total).to_contain_text("40,00")
    held.release(0)
    htmx_stil(page)
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    held.stop()
    htmx_stil(page)

    assert (first.input_value(), second.input_value()) == ("1", "1")
    assert "10,00" not in total.inner_text(), "the older answer arrived last and won"
    expect(total).to_contain_text("40,00")

    # What is saved and charged is what the fields say.
    page.fill("#contact_name", name)
    page.fill("#contact_email", "twee-wijzigingen@example.org")
    page.fill("#phone", "0470000000")
    page.locator('input[name="payment_method"][value="transfer"]').check()
    page.click("[data-form-save]")
    expect(page.locator("[data-payment-pending]")).to_contain_text("€ 40,00")
    assert _saved(setup["activity"], name) == {setup["first"]: 1, setup["second"]: 1}
    page.close()
