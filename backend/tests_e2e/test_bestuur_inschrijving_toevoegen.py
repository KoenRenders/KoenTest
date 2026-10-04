"""E2E: the board adds a registration from the activity's tab (#1192), at 390 px.

The path a board member takes on a phone: the activity's Inschrijvingen tab,
"+ Inschrijving toevoegen", the form, the quantity, Opslaan — and the new
registration's own page. It measures what that needs on a phone: the add button
and the save button lie inside the screen, and the form does not scroll sideways.

Broken on purpose to check that this test can go red: the `HX-Redirect` taken out
of the board route → the browser stays on the form and never reaches the
registration's page.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

WIDTH = 390


@pytest.fixture(scope="module")
def setup():
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole
    from tests.conftest import seed_activity_with_product

    db = SessionLocal()
    activity, _component, product = seed_activity_with_product(db, price="0", is_free=True)
    email = f"e2e-1192-{secrets.token_hex(3)}@example.org"
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()
    ids = {"activity": activity.id, "product": product.id}
    db.close()
    return {**ids, "session": make_session_value(email)}


@pytest.fixture(scope="module")
def page(setup):
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE, viewport={"width": WIDTH, "height": 844})
        login_met_sessie(p, setup["session"])
        yield p
        browser.close()


def _inside(locator) -> dict:
    box = locator.bounding_box()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= WIDTH, (
        f"outside the {WIDTH}px screen: {box}"
    )
    return box


def test_the_board_adds_a_registration_on_a_phone(page, setup):
    page.goto(f"/admin/activiteiten/{setup['activity']}/inschrijvingen")
    pagina_klaar(page)
    toevoegen = page.get_by_role("link", name="+ Inschrijving toevoegen")
    _inside(toevoegen)
    toevoegen.click()
    pagina_klaar(page)

    naam = f"Bestuur {secrets.token_hex(2)}"
    page.fill("#contact_name", naam)
    page.fill("#contact_email", "bestuur-e2e@example.org")
    page.fill("#phone", "0470000000")
    page.fill(f"#product-{setup['product']}", "8")
    page.fill("#remarks", "Acht namen van de papieren lijst")
    opslaan = page.get_by_role("button", name="Inschrijving toevoegen")
    _inside(opslaan)
    assert page.evaluate("document.documentElement.scrollWidth") <= WIDTH, (
        "the form scrolls sideways on a phone"
    )

    posts: list[str] = []
    page.on(
        "request", lambda r: posts.append(r.url.rsplit("/", 1)[-1]) if r.method == "POST" else None
    )
    opslaan.click()
    try:
        page.wait_for_url("**/admin/inschrijvingen/*", timeout=10_000)
    except Exception:
        # This test failed in CI without saying why (four runs of five on one
        # branch, 4 October 2026): the wait timed out and nothing was known about
        # the page. Say what stands on it — a refusal has a message, a click that
        # never landed has no POST.
        raise AssertionError(
            "no redirect to the registration after the save: "
            f"url={page.url!r} posts_after_click={posts} "
            f"quantity={page.locator(f'#product-{setup["product"]}').input_value()!r} "
            f"alerts={[t[:160] for t in page.locator('[role=alert], [data-field-error]').all_inner_texts()]} "
            f"busy={page.evaluate('() => [...document.querySelectorAll(".htmx-request")].map(e => e.id || e.tagName)')}"
        ) from None
    expect(page.get_by_text(naam).first).to_be_visible()
