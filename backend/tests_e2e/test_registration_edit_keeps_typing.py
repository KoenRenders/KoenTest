"""E2E: editing a registration in the back office, what is typed stays typed
when a counter recalculates the total (#1613).

Measured on master before the repair (5 October 2026, this file's setup): a
changed counter asked `/admin/inschrijvingen/<id>/totaal`, and the answer was
the WHOLE edit panel, drawn from the stored registration. So:

1. a name and a remark typed while that answer was under way were put back —
   the name to the stored one, the remark to empty — without a word;
2. text typed WHILE the answer landed was lost twice: what stood in the field
   went with the field, and the focus fell to the page, so the rest of the
   sentence went nowhere;
3. a second counter filled in meanwhile went back to its stored quantity, and
   the total was the one of the first change alone;
4. and, without any lateness at all: a name typed BEFORE the counter was
   changed was put back as soon as the total arrived — the panel was drawn
   from what is stored, not from what stood in it.

The repair is the pattern of #1596: the answer is the total and never a field;
the counters share one queue in which the newest request replaces the one under
way.

Each test holds the answer back in the browser (`schermen.Held`) and decides
itself when it lands.

Proven red against master `47bec4ca`, each test on its own: the messages are
the four numbered above (the name back to "Bewerk Proef", the remark empty, the
focus on BODY, the second counter back to "0").
"""

import os
import secrets
import sys
from decimal import Decimal

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, Held, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402

STORED_NAME = "Bewerk Proef"


@pytest.fixture(scope="module")
def setup():
    """A registration of one piece of the first product (10 euro); a second
    product (30 euro) of the same component, not chosen; a board member."""
    import httpx

    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.activities.api import ActivityProduct, Registration
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole
    from tests.conftest import seed_activity_with_product

    db = SessionLocal()
    activity, component, first = seed_activity_with_product(db, price="10.00", is_free=False)
    second = ActivityProduct(
        component_id=component.id, name="Tweede product", price=Decimal("30.00"), is_free=False
    )
    db.add(second)
    email = f"e2e-1613-{secrets.token_hex(3)}@example.org"
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()
    answer = httpx.post(
        f"{BASE}/api/v1/activities/{activity.id}/register",
        json={
            "contact_name": STORED_NAME,
            "contact_email": "bewerk-proef@example.org",
            "phone": "0470000000",
            "component_id": component.id,
            "payment_method": "transfer",
            "items": [{"product_id": first.id, "quantity": 1}],
        },
        timeout=30,
    )
    assert answer.status_code == 200, answer.text[:300]
    registration = db.query(Registration).filter_by(activity_id=activity.id).one().id
    out = {
        "page": f"/admin/inschrijvingen/{registration}",
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


@pytest.fixture
def panel(browser, setup):
    """The registration's page with its edit panel open. Nothing is saved by
    these tests: each starts from the stored registration."""
    page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 1000})
    login_met_sessie(page, setup["session"])
    page.goto(setup["page"])
    pagina_klaar(page)
    page.get_by_text("Bewerken", exact=True).first.click()
    page.locator("input[name^=product_]").first.wait_for(state="visible")
    assert page.input_value("[name=contact_name]") == STORED_NAME
    yield page
    page.close()


def _plus(page):
    return page.locator("[data-product-row] button[aria-label^='Eén meer']").first


def test_a_name_typed_before_the_counter_is_still_there_when_the_total_arrives(panel):
    """No lateness needed: the old answer drew the panel from what is stored."""
    panel.locator("[name=contact_name]").fill("Nieuwe Naam")
    with panel.expect_response(lambda r: r.url.endswith("/totaal")):
        _plus(panel).click()
    htmx_stil(panel)
    # The name first: on the old code this is what fails, not a missing element.
    assert panel.input_value("[name=contact_name]") == "Nieuwe Naam", (
        "the total's answer put the typed name back"
    )
    expect(panel.locator("[data-registration-total]")).to_contain_text("20,00")


def test_what_is_typed_while_the_total_is_under_way_stays(panel):
    held = Held(panel, "/totaal")
    _plus(panel).click()
    held.expect(1)
    panel.locator("[name=contact_name]").fill("Nieuwe Naam")
    panel.locator("[name=remarks]").fill("Getypt tijdens het wachten")
    held.stop()
    htmx_stil(panel)

    assert panel.input_value("[name=contact_name]") == "Nieuwe Naam"
    assert panel.input_value("[name=remarks]") == "Getypt tijdens het wachten"
    expect(panel.locator("[data-registration-total]")).to_contain_text("20,00")


def test_typing_goes_on_while_the_answer_lands(panel):
    held = Held(panel, "/totaal")
    _plus(panel).click()
    held.expect(1)
    panel.locator("[name=remarks]").click()
    panel.keyboard.insert_text("Eerste deel ")
    held.stop()
    htmx_stil(panel)
    panel.keyboard.insert_text("tweede deel")

    assert panel.evaluate("() => document.activeElement.name") == "remarks", (
        "the answer took the field away under the typist"
    )
    assert panel.input_value("[name=remarks]") == "Eerste deel tweede deel"


def test_a_second_counter_filled_in_meanwhile_keeps_its_quantity(panel, setup):
    held = Held(panel, "/totaal")
    _plus(panel).click()
    held.expect(1)
    second = panel.locator(f"input[name=product_{setup['second']}]")
    second.fill("3")
    held.stop()
    htmx_stil(panel)

    assert second.input_value() == "3", "the late answer put the second counter back"
    # 2 × 10 and 3 × 30: the total is the answer to the fields as they stand.
    expect(panel.locator("[data-registration-total]")).to_contain_text("110,00")
