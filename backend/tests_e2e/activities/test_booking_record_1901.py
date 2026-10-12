"""E2E #1901 (CR-11 roll-out, slice 3; end state §5.2 Boeking): the booking record on
the record layout, walked as the treasurer walks it.

Functionally nothing is lost (Koen: "functioneel moet het kunnen wat het nu kan
en dezelfde scenario's ondersteunen"). The scenarios, each in the browser:

1. **a transfer confirmed** — Bevestig is the primary of an open booking, with
   Bewerken beside it; afterwards the booking is settled and Bewerken is the
   primary;
2. **an amount corrected** — Bewerken opens the editor (the summary card stays),
   one Opslaan is one request, and the page reads again at its own address;
3. **a refund registered, corrected to 0 and deleted** — Terugbetaling
   registreren under Acties is a screen of its own: a refusal stands at the
   amount with its reason, a good answer lands on the NEW refund's page; the
   refund is paid out, corrected to 0 and then deleted, back on its charge;
4. **a booking deleted** — an open booking on which no money moved;
5. **the other bookings of the same registration** stand on the page as jump
   links (what an order change makes automatically is `reconcile_charges`',
   held in `tests/integration/test_reconcile_charges.py` and
   `test_order_changed.py`: no action on this page makes or needs it).

A manual extra charge is NOT built (Koen, 11 October 2026: whoever owes more
gets a product or a quantity on the registration, and the app makes the booking).

Measured: the summary card's rows on one x; the page no wider than the window
at 1 440 and 390 px.

Proven red (locally, restored), each by an addition:
- `edit=None` written over `edit=None if error else False` in the page's answer
  → "the editor is still open after the save";
- `X-Booking-Page` renamed on the editor's form → the save test fails waiting
  for the page in read mode (the list lands in the body);
- the refund route answering the charge's address → "the answer is not the new
  refund's page".
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar, toasts  # noqa: E402

TAG = uuid.uuid4().hex[:6]
DIALOG = "[data-dialog]"
BOOKINGS = "/admin/betalingen"


def _db():
    import app.main  # noqa: F401  the whole app: the handlers a registration publishes to
    from app.database import SessionLocal

    return SessionLocal()


def _seed() -> dict:
    """An activity with three registrations by transfer — a booking of € 20,00
    each — and beside the first registration's booking a second, paid one."""
    from fastapi import BackgroundTasks

    from app.domains.activities.api import (
        Activity,
        ActivityDate,
        ActivityProduct,
        ActivitySubRegistration,
        Registration,
        register_for_activity,
    )
    from app.domains.payment.api import PaymentRecord
    from app.schemas.activity import RegistrationCreate, RegistrationItemCreate

    db = _db()
    try:
        activity = Activity(name=f"Boekingen 1901 {TAG}")
        db.add(activity)
        db.flush()
        db.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=40)))
        component = ActivitySubRegistration(
            activity_id=activity.id,
            name="Etentje",
            registration_type_code="INDIVIDUAL",
            price=Decimal("0"),
            is_free=True,
        )
        db.add(component)
        db.flush()
        product = ActivityProduct(
            component_id=component.id, name="Soep", price=Decimal("10.00"), is_free=False
        )
        db.add(product)
        db.commit()
        bookings = {}
        for key in ("confirm", "refund", "delete"):
            register_for_activity(
                db,
                activity.id,
                RegistrationCreate(
                    contact_name=f"{key.title()} Boeker",
                    contact_email=f"e2e-1901-{key}-{TAG}@example.org",
                    phone="0470000000",
                    component_id=component.id,
                    payment_method="transfer",
                    items=[RegistrationItemCreate(product_id=product.id, quantity=2)],
                ),
                BackgroundTasks(),
            )
            registration = (
                db.query(Registration)
                .filter(Registration.activity_id == activity.id)
                .order_by(Registration.id.desc())
                .first()
            )
            record = (
                db.query(PaymentRecord)
                .filter_by(payable_type="registration", payable_id=registration.id)
                .one()
            )
            bookings[key] = str(record.id)
            if key == "confirm":
                extra = PaymentRecord(
                    payable_type="registration",
                    payable_id=registration.id,
                    type="charge",
                    amount=Decimal("5.00"),
                    amount_paid=Decimal("5.00"),
                    method="transfer",
                    status="paid",
                    structured_communication="+++000/0000/01901+++",
                )
                db.add(extra)
                db.commit()
                bookings["other"] = str(extra.id)
        return {"activity": activity.id, **bookings}
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    """The activity stays: one with registrations is not deleted, as the seed's
    own are not (`test_activity_tabs.py` leaves its activity too)."""
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    made = _seed()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), made
        b.close()


def _page(setup, address: str, width: int = 1440):
    b, session, _made = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.posts = []
    page.on("request", lambda r: page.posts.append(r.url) if r.method == "POST" else None)
    login_met_sessie(page, session)
    page.goto(address)
    pagina_klaar(page)
    return page


def _stored(record_id: str):
    """(status, amount received, note) of a booking, or None when it is gone (a
    deleted booking is no longer read)."""
    from app.domains.payment.api import PaymentRecord

    db = _db()
    try:
        record = db.get(PaymentRecord, record_id)
        return (
            None
            if record is None
            else (
                str(getattr(record.status, "value", record.status)),
                record.amount_paid,
                record.note,
                record.deleted_at is not None,
            )
        )
    finally:
        db.close()


def _refund_of(record_id: str):
    from app.domains.payment.api import PaymentRecord

    db = _db()
    try:
        refund = db.query(PaymentRecord).filter(PaymentRecord.refund_of_id == record_id).first()
        return None if refund is None else str(refund.id)
    finally:
        db.close()


def _script_errors(page) -> list[str]:
    """What the page threw — without the browser's notice that a view transition
    was cut short: this walk clicks the next command while the page that answered
    the last one is still fading in, which no person does and no script causes."""
    return [e for e in page.errors if "Transition was skipped" not in e]


def _confirm(page) -> None:
    page.locator(f"{DIALOG}:visible").wait_for()
    page.click(f"{DIALOG} [data-dialog-ok]")


_SHAPE = """() => { const q = s => document.querySelector(s), all = s => [...document.querySelectorAll(s)];
  const r = e => e.getBoundingClientRect();
  const card = q('[data-summary-card]');
  return {mode: q('[data-form-flow]').dataset.mode, heads: all('[data-record-head]').length, shells: all('#admin-zijbalk').length,
          figures: [...card.querySelectorAll('[data-summary-figure]')].map(f => ({
              label: f.querySelector('dt').innerText.trim(), value: f.querySelector('dd').innerText.trim(),
              left: Math.round(r(f.querySelector('dt')).left), right: Math.round(r(f.querySelector('dd')).right)})),
          sections: all('[data-form-flow] [data-form-section] h2').map(h => h.innerText.trim()),
          controls: all('[data-head-controls] a, [data-head-controls] > button').map(e => e.innerText.trim()),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize("width", [1440, 390])
def test_an_open_booking_reads_first_with_its_summary_and_the_other_bookings(setup, width):
    _b, _session, made = setup
    page = _page(setup, f"{BOOKINGS}/{made['confirm']}", width)
    try:
        seen = page.evaluate(_SHAPE)
        print("MEASURE booking read", width, seen)
        assert seen["mode"] == "read" and seen["heads"] == 1 and seen["shells"] == 1
        assert [f["label"] for f in seen["figures"]] == [
            "Bedrag",
            "Ontvangen",
            "Saldo",
            "Wijze",
            "Aangemaakt",
        ]
        assert (
            seen["figures"][0]["value"] == "€ 20,00"
            and seen["figures"][3]["value"] == "Overschrijving"
        )
        assert len({f["left"] for f in seen["figures"]}) == 1, "the labels share no left edge"
        assert len({f["right"] for f in seen["figures"]}) == 1, "the values share no right edge"
        assert seen["sections"] == ["Boeking", "Andere boekingen van deze inschrijving"]
        assert seen["controls"][:2] == ["Bevestig", "Bewerken"], seen["controls"]
        other = page.locator(f'[data-booking-others] a[href^="{BOOKINGS}/{made["other"]}"]')
        expect(other).to_have_count(1)
        assert page.locator("[data-form-flow] form").count() == 0, "read mode carries a form"
        assert seen["page"][0] == seen["page"][1], "wider than the window"
        assert page.errors == []
    finally:
        page.close()


def test_a_transfer_is_confirmed_and_an_amount_corrected(setup):
    _b, _session, made = setup
    address = f"{BOOKINGS}/{made['confirm']}"
    page = _page(setup, address)
    try:
        # 1. Bevestig: the whole amount, in one click and its question.
        page.locator('[data-head-controls] button:has-text("Bevestig")').click()
        _confirm(page)
        expect(page.locator("[data-record-head] [data-badges]")).to_contain_text("Vereffend")
        assert _stored(made["confirm"])[:2] == ("paid", Decimal("20.00"))
        controls = page.evaluate(_SHAPE)["controls"]
        assert controls[0] == "Bewerken" and "Bevestig" not in controls, controls

        # 2. Bewerken: the editor, with the summary beside it; one save, one request.
        page.locator('[data-head-controls] a:has-text("Bewerken")').click()
        page.wait_for_url("**bewerken=1")
        pagina_klaar(page)
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "edit")
        expect(page.locator("[data-summary-card]")).to_be_visible()
        page.locator("#bk-amount-paid").fill("15.00")
        page.locator("#bk-note").fill("voorschot")
        page.posts.clear()
        page.locator("[data-form-save]").first.click()
        expect(
            page.locator("[data-form-flow]"), "the editor is still open after the save"
        ).to_have_attribute("data-mode", "read")
        pagina_klaar(page)
        assert len(page.posts) == 1, page.posts
        seen = page.evaluate(_SHAPE)
        assert seen["heads"] == 1 and seen["shells"] == 1, "the page nested or lost its head"
        facts = page.locator("[data-booking-facts]").inner_text()
        assert "Betaald bedrag: € 15,00" in facts and "Opmerking: voorschot" in facts, facts
        assert toasts(page).count() >= 1, "no confirmation after the save"
        assert page.url.endswith(address), f"the address kept its edit flag: {page.url}"
        # € 15,00 of € 20,00: the booking is partly paid, and says so.
        assert _stored(made["confirm"])[1:3] == (Decimal("15.00"), "voorschot")
        expect(page.locator("[data-record-head] [data-badges]")).to_contain_text("Deels betaald")
        assert _script_errors(page) == []
    finally:
        page.close()


def test_a_refund_is_registered_corrected_to_zero_and_deleted(setup):
    _b, _session, made = setup
    charge = f"{BOOKINGS}/{made['refund']}"
    page = _page(setup, charge)
    try:
        page.locator('[data-head-controls] button:has-text("Bevestig")').click()
        _confirm(page)
        expect(page.locator("[data-record-head] [data-badges]")).to_contain_text("Vereffend")

        # The screen of its own, from Acties.
        page.click("[data-actions-trigger]")
        page.get_by_role("menuitem", name="Terugbetaling registreren").click()
        page.wait_for_url(f"**{charge}/terugbetaling**")
        pagina_klaar(page)
        expect(page.locator("h1")).to_have_text("Terugbetaling registreren")
        expect(page.locator("[data-refund-received]")).to_contain_text("€ 20,00")

        # A refusal stands on the screen, with its reason; nothing is made.
        page.locator("#bk-refund-amount").fill("1000")
        page.locator("[data-form-save]").first.click()
        banner = page.locator("#terugbetaling-melding [data-save-refusal]")
        expect(banner).to_be_visible()
        assert "terugbetalen" in banner.inner_text() and "20,00" in banner.inner_text()
        # The kit shows a refusal in two steps (#1908): the banner comes with the
        # answer's swap, and one settle later — 20 ms — the reason stands at the
        # field and the focus moves to it. This test typed in between: the focus
        # left the Reden field for the amount while its text was on the way, so
        # "annulering" landed in the number field and the save posted an empty
        # amount and an empty reason (measured: 9 of 80 walks). The refusal is
        # shown when its reason stands at the field; only then is typing safe.
        expect(page.locator('[data-field="amount"] [data-refused-message]')).to_contain_text(
            "terugbetalen"
        )
        expect(page.locator("#bk-refund-amount")).to_be_focused()
        assert _refund_of(made["refund"]) is None, "a refused refund was made"

        # A good answer lands on the NEW refund's page.
        page.locator("#bk-refund-amount").fill("5")
        page.locator("#bk-refund-note").fill("annulering")
        page.locator("[data-form-save]").first.click()
        page.wait_for_url(lambda url: "/terugbetaling" not in url and BOOKINGS + "/" in url)
        pagina_klaar(page)
        refund = _refund_of(made["refund"])
        assert refund and f"{BOOKINGS}/{refund}" in page.url, (
            f"the answer is not the new refund's page: {page.url}"
        )
        expect(page.locator("h1")).to_contain_text("Terugbetaling aan")
        assert page.locator("[data-booking-parent] a").get_attribute("href").startswith(charge)

        # Paid out, then corrected to 0, then deleted — back on its charge.
        page.locator('[data-head-controls] button:has-text("Bevestig")').click()
        _confirm(page)
        expect(page.locator("[data-record-head] [data-badges]")).to_contain_text("Vereffend")
        assert _stored(refund)[1] == Decimal("-5.00")
        page.locator('[data-head-controls] a:has-text("Bewerken")').click()
        page.wait_for_url("**bewerken=1")
        pagina_klaar(page)
        expect(page.locator('label[for="bk-amount-paid"]')).to_contain_text("Terugbetaald bedrag")
        expect(page.locator("#bk-boeking")).to_contain_text("Zet op 0 om te corrigeren")
        page.locator("#bk-status").select_option("pending")
        page.locator("#bk-amount-paid").fill("0")
        page.locator("[data-form-save]").first.click()
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        pagina_klaar(page)
        page.click("[data-actions-trigger]")
        page.get_by_role("menuitem", name="Verwijderen").click()
        _confirm(page)
        page.wait_for_url(lambda url: url.split("?")[0].endswith(charge))
        pagina_klaar(page)
        assert _stored(refund) is None, "the refund is still there"
        expect(page.locator("[data-booking-refunds]")).to_have_count(0)
        assert _script_errors(page) == []
    finally:
        page.close()


def test_an_open_booking_without_money_is_deleted(setup):
    _b, _session, made = setup
    page = _page(setup, f"{BOOKINGS}/{made['delete']}?terug=/admin/betalingen")
    try:
        page.click("[data-actions-trigger]")
        page.get_by_role("menuitem", name="Verwijderen").click()
        _confirm(page)
        page.wait_for_url(lambda url: url.rstrip("/").endswith(BOOKINGS))
        pagina_klaar(page)
        assert _stored(made["delete"]) is None, "the booking is still there"
        assert page.errors == []
    finally:
        page.close()
