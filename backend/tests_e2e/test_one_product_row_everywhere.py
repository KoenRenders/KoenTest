"""E2E: one product row in the three screens, measured on the rendered page (#1287).

Koen, validating v2.7.0: editing a registration in the back office still had the old
arrows, not − and +. And the line amount (2 × €15 = €30) — he decided it goes
everywhere, since the registration form never had it. So the three screens —
registering (public), adding (board) and editing (board) — render the same row:
name, unit price, a counter. This test opens each, at 390 and at 1280 px, and
measures on the DOM:

- every visible product row has the counter's two buttons, and the `+` is really
  clickable — `elementFromPoint` on its centre finds it (#1200 was a `+` clipped
  out of reach);
- a quantity raised with `+` moves the total, and no row carries that amount:
  there is no line amount;
- on the edit screen the "Product toevoegen" quantity is a counter too;
- nothing sticks out of the screen.

It counts before it measures: each screen must show at least one product row.

Proven red against master `4b5e96f7` (29 September 2026): the public and board
screens passed, the edit screen failed at both widths with "no counter in the
row" — the `type="number"` field Koen reported.
"""

import os
import sys
from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def setup():
    """A paid component at €10 and a board member."""
    import secrets

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole
    from tests.conftest import seed_activity_with_product

    db = SessionLocal()
    activity, component, product = seed_activity_with_product(db, price="10.00")
    product.max_participants = None
    email = f"e2e-1287-{secrets.token_hex(3)}@example.org"
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()
    out = {
        "activity": activity.id,
        "component": component.id,
        "product": product.id,
        "price": Decimal("10.00"),
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


@pytest.fixture(scope="module")
def registration(setup):
    """A registration of 2, made through the registration service — the one the
    public form uses — and not through a JSON route (CR-13 phase 4b: the route had
    no caller but this set-up)."""
    from fastapi import BackgroundTasks

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import RegistrationCreate, register_for_activity

    db = SessionLocal()
    try:
        result = register_for_activity(
            db,
            setup["activity"],
            RegistrationCreate(
                contact_name="E2E Regel",
                phone="0470000000",
                contact_email="regel@example.com",
                component_id=setup["component"],
                payment_method="transfer",
                items=[{"product_id": setup["product"], "quantity": 2}],
            ),
            BackgroundTasks(),
        )
    finally:
        db.close()
    return result["id"]


def _page(browser, width, session=None):
    context = browser.new_context(base_url=BASE, viewport={"width": width, "height": 900})
    page = context.new_page()
    if session:
        login_met_sessie(page, session)
    return context, page


# The rows are found from their quantity fields, not from the row's own marker, so
# the same measurement runs against code that predates the shared row.
_ROWS = """() => [...new Set([...document.querySelectorAll(
    'input[name^="product_"], input[name^="quantity_"]')]
  .map(f => f.closest('[data-product-row]') || f.closest('div.flex')))]
  .filter(r => r && r.offsetParent !== null)
  .map(r => {
    r.scrollIntoView({block: 'center'});
    const labels = [...r.querySelectorAll('button[aria-label]')].map(b => b.getAttribute('aria-label'));
    const plus = [...r.querySelectorAll('button[aria-label]')]
      .find(b => b.getAttribute('aria-label').startsWith('Eén meer'));
    let reachable = false;
    if (plus) {
      const p = plus.getBoundingClientRect();
      const hit = document.elementFromPoint(p.left + p.width / 2, p.top + p.height / 2);
      reachable = hit === plus || plus.contains(hit);
    }
    const b = r.getBoundingClientRect();
    return {text: r.innerText.replace(/\\s+/g, ' ').trim(), labels, reachable,
            height: Math.round(b.height), right: Math.round(b.right), vw: innerWidth,
            doc: document.documentElement.scrollWidth};
  })"""


def _check_rows(page, label: str) -> list[dict]:
    # A condition, not a pause (#997): the public form opens in a modal that slides
    # in, and during that transition nothing is under the pointer yet.
    try:
        page.wait_for_function(
            f"() => {{ const rows = ({_ROWS})(); return rows.length && rows.every(r => r.reachable); }}",
            timeout=3000,
        )
    except Exception:
        pass  # the assertions below say what is wrong
    rows = page.evaluate(_ROWS)
    assert rows, f"{label}: no product row on the screen"
    for row in rows:
        assert any(x.startswith("Eén minder") for x in row["labels"]) and any(
            x.startswith("Eén meer") for x in row["labels"]
        ), f"{label}: no counter in the row: {row}"
        assert row["reachable"], f"{label}: the + cannot be clicked: {row}"
        assert row["doc"] <= row["vw"], f"{label}: {row['doc']} px wide at {row['vw']} px"
    return rows


def _plus(page, product_id: int) -> None:
    field = page.locator(f'input[name="product_{product_id}"], input[name^="quantity_"]').first
    field.locator("xpath=../button[starts-with(@aria-label,'Eén meer')]").click()
    htmx_stil(page)


def _no_line_amount(page, amount: str, label: str) -> None:
    texts = [r["text"] for r in page.evaluate(_ROWS)]
    assert not [t for t in texts if amount in t], f"{label}: a line amount {amount} in {texts}"


@pytest.mark.parametrize("width", [390, 1280])
def test_registering_and_adding_have_the_one_row(browser, setup, width):
    context, public = _page(browser, width)
    try:
        public.goto("/activiteiten")
        public.click(
            f'button[hx-get="/activiteiten/{setup["activity"]}/inschrijven/{setup["component"]}"]'
        )
        public.wait_for_selector("#contact_email")
        htmx_stil(public)
        _check_rows(public, f"public @{width}")
        _plus(public, setup["product"])  # 1 → 2
        assert "€20,00" in public.locator('[id^="totaal-"]').inner_text()
        _no_line_amount(public, "20,00", f"public @{width}")
    finally:
        context.close()

    context, board = _page(browser, width, setup["session"])
    try:
        board.goto(f"/admin/activiteiten/{setup['activity']}/inschrijvingen/nieuw")
        pagina_klaar(board)
        _check_rows(board, f"board @{width}")
        _plus(board, setup["product"])
        assert "€20,00" in board.locator('[id^="totaal-"]').inner_text()
        _no_line_amount(board, "20,00", f"board @{width}")
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_editing_has_the_one_row(browser, setup, registration, width):
    context, page = _page(browser, width, setup["session"])
    try:
        page.goto(f"/admin/inschrijvingen/{registration}")
        pagina_klaar(page)
        panel = page.locator("div.bg-gray-50.border", has=page.locator('form[id^="insch-form-"]'))
        panel.first.get_by_role("button", name="Bewerken").first.click()
        rows = _check_rows(page, f"edit @{width}")
        assert all("Verwijderen" in r["text"] for r in rows), rows

        _plus(page, setup["product"])  # 2 → 3, recalculated, not stored
        form = page.locator('form[id^="insch-form-"]').first
        assert "30,00" in form.inner_text(), "the total does not follow the counter"
        _no_line_amount(page, "30,00", f"edit @{width}")

        adding = form.locator('input[name="quantity"]')
        assert adding.count() == 1, "no quantity for Product toevoegen"
        assert (
            adding.locator("xpath=../button[starts-with(@aria-label,'Eén meer')]").count() == 1
        ), "Product toevoegen has no counter"
    finally:
        context.close()
