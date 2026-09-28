"""E2E: the board's form is the public one, measured on the rendered page (#1284).

Koen, on HDEV: the board's "add a registration" form showed no amounts. It now
renders the public form's fields. This test opens the same paid component in both
channels — the public modal and the board's page — at 390 px and at 1280 px, and
measures on the DOM what the issue asks:

- each product row shows its price;
- the total is there and follows a quantity change (server-side, `/totaal`);
- the payment choice is there, `online` included;
- on the board, typing a member's address turns the total into the member price;
- nothing sticks out of the screen.

It counts before it measures: the form, its product row and its total must be
there, so an empty screen cannot pass.

Proven red on the old code (28 September 2026): the same test against a server
built from `origin/master` before #1284 failed at both widths on the board, with
"no price on the product row: 'Testproduct − +'" — the product name and a
stepper, nothing else. That is the screen Koen reported.

The member-row check (Koen's answer, #1284 reopened) was proven red the same way:
against `origin/master` at c4f1ffe7 the row stayed "Testproduct €10,00" after a
member's address was typed — only the total followed it.
"""
import os
import re
import secrets
import sys
from datetime import date
from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def setup():
    """A paid component (€10, €6 for members), a member with a valid membership,
    and a board member."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole
    from app.domains.membership.api import Membership
    from tests.conftest import create_test_family, seed_activity_with_product

    db = SessionLocal()
    activity, component, product = seed_activity_with_product(db, price="10.00")
    product.member_price = Decimal("6.00")
    member_email = f"e2e-lid-1284-{secrets.token_hex(3)}@example.org"
    household, _person = create_test_family(db, email=member_email)
    year = date.today().year
    db.add(Membership(member_id=household.id, year=year, is_active=True,
                      valid_from=date(year, 1, 1), valid_to=date(year, 12, 31)))
    board_email = f"e2e-1284-{secrets.token_hex(3)}@example.org"
    user = User(email=board_email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()
    out = {"activity": activity.id, "component": component.id, "product": product.id,
           "member": member_email, "session": make_session_value(board_email)}
    db.close()
    return out


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _page(browser, width: int, session: str | None = None):
    context = browser.new_context(base_url=BASE, viewport={"width": width, "height": 900})
    page = context.new_page()
    if session:
        login_met_sessie(page, session)
    return context, page


_MEASURE = """(productId) => {
  const form = document.querySelector('input[name="contact_email"]').closest('form');
  const row = form.querySelector('input[name="product_' + productId + '"]');
  const rowText = row ? row.closest('.flex').innerText : '';
  const total = form.querySelector('[id^="totaal-"]');
  const vw = window.innerWidth;
  const outside = [...form.querySelectorAll('*')].filter(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && (Math.round(r.right) > vw || Math.round(r.left) < 0);
  }).map(e => e.tagName.toLowerCase() + ' "' + (e.innerText || e.value || '').trim().slice(0, 25) + '"');
  return {
    row: !!row, rowText,
    total: total ? total.innerText.trim() : null,
    online: !!form.querySelector('input[name="payment_method"][value="online"]'),
    doc: document.documentElement.scrollWidth, vw, outside,
  };
}"""


_ROW = """(pid) => document.querySelector('input[name="product_' + pid + '"]')
  .closest('.flex').innerText.split('\\n')[0]"""


def _open_public(page, setup):
    page.goto("/activiteiten")
    page.click(f'button[hx-get="/activiteiten/{setup["activity"]}/inschrijven/{setup["component"]}"]')
    page.wait_for_selector("#contact_email")
    htmx_stil(page)


def _open_board(page, setup):
    page.goto(f"/admin/activiteiten/{setup['activity']}/inschrijvingen/nieuw")
    pagina_klaar(page)


def _check(page, setup, label: str) -> dict:
    m = page.evaluate(_MEASURE, setup["product"])
    assert m["row"], f"{label}: no product row"
    assert "€10,00" in m["rowText"], f"{label}: no price on the product row: {m['rowText']!r}"
    assert m["total"] and m["total"].startswith("Totaal:"), f"{label}: no total: {m['total']!r}"
    assert m["online"], f"{label}: no online payment"
    assert m["doc"] <= m["vw"] and not m["outside"], (
        f"{label}: {m['doc']} px wide at {m['vw']} px; sticking out: {m['outside']}")
    return m


def _set_quantity(page, setup, quantity: int) -> str:
    field = page.locator(f'input[name="product_{setup["product"]}"]')
    field.fill(str(quantity))
    field.dispatch_event("change")
    htmx_stil(page)
    return page.locator('[id^="totaal-"]').inner_text().strip()


@pytest.mark.parametrize("width", [390, 1280])
def test_both_channels_show_prices_a_live_total_and_online(browser, setup, width):
    context, public = _page(browser, width)
    try:
        _open_public(public, setup)
        _check(public, setup, f"public @{width}")
        assert "€20,00" in _set_quantity(public, setup, 2)
    finally:
        context.close()

    context, board = _page(browser, width, setup["session"])
    try:
        _open_board(board, setup)
        _check(board, setup, f"board @{width}")
        assert "€20,00" in _set_quantity(board, setup, 2)
        # The board's member price follows the TYPED address — rows and total,
        # the entered quantity kept, and the address field keeps its focus
        # (Koen, #1284: "ja, de productregel volgt het ingetypte ledenadres").
        row_before = board.evaluate(_ROW, setup["product"])
        board.fill("#contact_email", setup["member"])
        board.locator("#contact_email").dispatch_event("change")
        htmx_stil(board)
        total = board.locator('[id^="totaal-"]').inner_text().strip()
        assert "€12,00" in total and "ledenprijs" in total, total
        row_after = board.evaluate(_ROW, setup["product"])
        assert "/ leden €6,00" not in row_before and "€10,00 / leden €6,00" in row_after, (
            row_before, row_after)
        assert board.locator(f'input[name="product_{setup["product"]}"]').input_value() == "2"
        assert board.evaluate("document.activeElement && document.activeElement.id") == "contact_email"
        _check(board, setup, f"board @{width}, member")
    finally:
        context.close()
