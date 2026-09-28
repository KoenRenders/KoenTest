"""The online payment chain, walked in a browser with the stub provider (#1274).

Until now every e2e path chose *overschrijving*, because online payment went to
Mollie — so nothing tested the chain Koen walked by hand on UAT: choose online,
be sent to the payment page, pay, come back on `/betaling/succes`, let the
webhook fetch the status, and see the new state on screen. This test walks it
twice, for a registration and for *Word lid*, with the stub provider
(`PAYMENT_PROVIDER=stub`, allowed only in development and the tests).

**The chain runs through the real security rule.** The stub starts at *open*.
Before paying, the test fires the webhook itself — only an id, as Mollie sends —
and the screen must still say the payment is pending. Only after the pretend
payment does the same webhook make it paid. A stub that always said *paid*
would pass this chain even if the webhook believed its own body; this one fails
it (see the proof below).

Needs the e2e seed and `PAYMENT_PROVIDER=stub` on the server; without it the
form goes to Mollie and the test says so instead of failing somewhere later.

Broken on purpose (28 September 2026): the stub made to start at *paid* instead
of *open* → both tests failed on the step before the payment, with "paid before
anyone paid" (the booking already *Vereffend*) and "active before anyone paid"
(the membership already *Actief*). That is the proof the webhook fetches its
status from the provider and does not take it from anywhere else.
"""

import os
import re
import sys
import time

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin, pagina_klaar  # noqa: E402

WEBHOOK = "/api/v1/payment-gateway/webhooks/stub"
CHECKOUT = re.compile(r"/betaling/stub/(stub_[0-9a-f]+)$")


@pytest.fixture(scope="module")
def paid_activity():
    """An open activity with one paid product, through the same database as the
    running server."""
    from datetime import date, timedelta
    from decimal import Decimal

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import (
        Activity,
        ActivityDate,
        ActivityProduct,
        ActivitySubRegistration,
    )

    db = SessionLocal()
    activity = Activity(name=f"E2E Online betalen {int(time.time())}")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=30)))
    component = ActivitySubRegistration(
        activity_id=activity.id, name="Deelname", price=Decimal("0"), is_free=True
    )
    db.add(component)
    db.flush()
    product = ActivityProduct(
        component_id=component.id, name="Ticket", price=Decimal("12.50"), is_free=False
    )
    db.add(product)
    db.commit()
    ids = (activity.id, component.id, product.id)
    db.close()
    return ids


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def visitor(browser):
    context = browser.new_context(base_url=BASE, viewport={"width": 390, "height": 844})
    yield context.new_page()
    context.close()


@pytest.fixture
def admin(browser):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    context = browser.new_context(base_url=BASE, viewport={"width": 1280, "height": 900})
    page = context.new_page()
    login_als_admin(page, email, make_session_value(email))
    yield page
    context.close()


def _at_the_checkout(page) -> str:
    """Waits for the pretend payment page and returns the stub's payment id."""
    try:
        page.wait_for_url(CHECKOUT, timeout=10_000)
    except Exception:
        pytest.fail(
            f"not sent to the stub's payment page but to {page.url} — is "
            f"PAYMENT_PROVIDER=stub set on the e2e server?"
        )
    expect(page.get_by_role("heading", name=re.compile("Testbetaling"))).to_be_visible()
    return CHECKOUT.search(page.url).group(1)


def _fire_webhook(page, payment_id: str) -> None:
    """What Mollie's server does: POST the id, nothing else."""
    answer = page.request.post(WEBHOOK, form={"id": payment_id})
    assert answer.ok and answer.json() == {"status": "ok"}, answer.text()


def _payable_id(payment_id: str) -> int:
    """Which registration or household the stub payment is for — read from the
    gateway payment the server stored, the way the webhook finds it."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.payment.models import GatewayPayment

    db = SessionLocal()
    try:
        gp = db.query(GatewayPayment).filter(GatewayPayment.provider_payment_id == payment_id).one()
        return int(gp.payment_metadata["payable_id"])
    finally:
        db.close()


def _household_of_membership(membership_id: int) -> int:
    """A membership payment is for a membership; the screen is the household's."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.membership.api import Membership

    db = SessionLocal()
    try:
        return int(db.get(Membership, membership_id).member_id)
    finally:
        db.close()


def _pay(page, query_key: str) -> int:
    page.get_by_role("button", name="Betaal").click()
    page.wait_for_url(re.compile(rf"/betaling/succes\?{query_key}=\d+"), timeout=10_000)
    return int(re.search(rf"{query_key}=(\d+)", page.url).group(1))


def _status_badges(admin, registration_id: int) -> list[str]:
    """The status badge of each payment row on the registration's Betalingen tab
    — the badge, not the page text: "Betaald" is also a column heading there.
    A booking reads *Openstaand* until it is paid and *Vereffend* after."""
    admin.goto(f"/admin/inschrijvingen/{registration_id}/betalingen")
    pagina_klaar(admin)
    badges = admin.evaluate("""() => [...document.querySelectorAll(
        '#betalingen-lijst tbody span.rounded-full')].map(b => b.innerText.trim())
        .filter(t => t)""")
    assert badges, "no payment row with a status badge on the tab"
    return badges


def test_a_registration_is_paid_online(visitor, admin, paid_activity):
    activity_id, component_id, product_id = paid_activity
    visitor.goto("/activiteiten")
    visitor.click(f'button[hx-get="/activiteiten/{activity_id}/inschrijven/{component_id}"]')
    visitor.fill("#contact_name", "E2E Online")
    visitor.fill("#contact_email", f"e2e+online{int(time.time() * 1000)}@example.com")
    visitor.fill("#phone", "0470000000")
    visitor.fill(f'input[name="product_{product_id}"]', "1")
    visitor.check('input[name="payment_method"][value="online"]')
    visitor.locator(f"#inschrijf-{activity_id}-{component_id} button[type=submit]").click()
    payment_id = _at_the_checkout(visitor)

    registration_id = _payable_id(payment_id)

    # The webhook BEFORE the payment. It carries only the id; the status comes
    # from the stub, which still says open — so the screen must still say so.
    _fire_webhook(visitor, payment_id)
    before = _status_badges(admin, registration_id)
    assert "Openstaand" in before and "Vereffend" not in before, (
        f"paid before anyone paid: {before}"
    )

    # Pay on the pretend page; the page fires the webhook and returns the visitor.
    assert _pay(visitor, "registration") == registration_id
    after = _status_badges(admin, registration_id)
    assert "Vereffend" in after and "Openstaand" not in after, (
        f"not settled after the payment: {after}"
    )


def _membership_line(admin, member_id: int) -> str:
    """The household's Lidmaatschappen block on its admin page, one line."""
    admin.goto(f"/admin/leden/gezin/{member_id}")
    pagina_klaar(admin)
    block = admin.get_by_text("Lidmaatschappen", exact=True).locator("xpath=..")
    return " ".join(block.inner_text().split())


def _valid_to(membership_id: int):
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.membership.api import Membership

    db = SessionLocal()
    try:
        return db.get(Membership, membership_id).valid_to
    finally:
        db.close()


def test_word_lid_is_paid_online(visitor, admin):
    from datetime import date

    from app.domains.payment.api import membership_valid_period

    visitor.goto("/lid-worden")
    visitor.fill("#m0_first_name", "Online")
    visitor.fill("#m0_last_name", "Gezin")
    visitor.fill("#m0_email", f"e2e+lid{int(time.time() * 1000)}@example.com")
    visitor.fill("#m0_mobile", "0470000000")
    visitor.fill("#m0_date_of_birth", "1980-01-01")
    visitor.select_option("#m0_gender_code", "M")
    visitor.fill("#street", "Teststraat")
    visitor.fill("#house_number", "1")
    visitor.select_option("#postal_code", index=1)
    visitor.check('input[name="payment_method"][value="online"]')
    visitor.click('button[type="submit"]')
    payment_id = _at_the_checkout(visitor)
    membership_id = _payable_id(payment_id)
    member_id = _household_of_membership(membership_id)

    # The webhook BEFORE the payment: the membership stays inactive.
    _fire_webhook(visitor, payment_id)
    before = _membership_line(admin, member_id)
    assert "Inactief" in before, f"active before anyone paid: {before}"

    assert _pay(visitor, "member") == member_id
    after = _membership_line(admin, member_id)
    assert "Actief" in after and "Inactief" not in after, after
    # And it runs as long as the domain's own rule says a payment today buys —
    # through the end of next year after 1 September (`membership_valid_period`).
    assert _valid_to(membership_id) == membership_valid_period(date.today())[1]
