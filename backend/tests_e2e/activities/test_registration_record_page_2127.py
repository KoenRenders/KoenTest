"""E2E: a registration is a record page with ONE save (#2127; CR-11 phase 5, round 4).

Walked in the browser: the record head with the payment state, the activity as a fact
and the tabs; Bewerken opens the editor on the same page (contact, products, the
answers to the component's questions); one Opslaan stores a changed name, a changed
counter and a changed answer together and answers the read page with the toast; a
refused save keeps what was typed and says why at the field; at 390 and 1 100 px the
page does not scroll sideways, read and edit. When `E2E_PRINT_DIR` is set a print of
the read and of the edit state is taken at both widths (looked at by whoever hands the
work over).

Broken on purpose (19 October 2026, each put back): the savepoint rollback of
`registration_save` taken out → the refusal test finds the typed name stored; the
`ui.error_banner`/refusal target `#insch-melding` renamed → the refusal test finds no
banner at the field.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, login_met_sessie, pagina_klaar  # noqa: E402

STORED_NAME = "Rik Record"


@pytest.fixture(scope="module")
def setup():
    """A registration of one product, with answers to the component's questions, and a
    board member. A second one for the refusal, so the tests do not meet each other."""
    from fastapi import BackgroundTasks

    import app.main  # noqa: F401
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.activities.api import register_for_activity
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole
    from app.schemas.activity import RegistrationCreate, RegistrationItemCreate
    from tests.conftest import ask_questions, seed_activity_with_product, seed_question_form

    db = SessionLocal()
    activity, component, product = seed_activity_with_product(db, price="10.00", is_free=False)
    form = seed_question_form(db)
    ask_questions(db, component, form.id)
    slot = next(f for f in form.fields if f.label == "Tijdslot")
    story = next(f for f in form.fields if f.label == "Verhaal")
    email = f"e2e-2127-{secrets.token_hex(3)}@example.org"
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()

    def register(name: str) -> int:
        result = register_for_activity(
            db,
            activity.id,
            RegistrationCreate(
                contact_name=name,
                contact_email=f"{secrets.token_hex(3)}@example.org",
                phone="0470000000",
                component_id=component.id,
                payment_method="transfer",
                items=[RegistrationItemCreate(product_id=product.id, quantity=2)],
                answers=[
                    {"field_id": slot.id, "option_ids": [slot.options[0].id]},
                    {"field_id": story.id, "text": "Braaf"},
                ],
            ),
            BackgroundTasks(),
        )
        return result["id"] if isinstance(result, dict) else result.id

    out = {
        "save": register(STORED_NAME),
        "refuse": register("Weiger Proef"),
        "session": make_session_value(email),
        "product": product.id,
        "story": story.id,
        "activity": activity.name,
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


def _page(browser, setup, width):
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, setup["session"])
    return page


def _print(page, name, width):
    folder = os.environ.get("E2E_PRINT_DIR")
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    height = page.evaluate("document.documentElement.scrollHeight")
    page.set_viewport_size({"width": width, "height": max(900, min(height, 3600))})
    page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    page.screenshot(path=os.path.join(folder, f"{name}-{width}.png"), caret="initial")


def test_the_head_and_one_save_of_a_changed_name_counter_and_answer(browser, setup):
    page = _page(browser, setup, 1100)
    try:
        page.goto(f"/admin/inschrijvingen/{setup['save']}")
        pagina_klaar(page)
        head = page.locator("[data-record-head]")
        expect(head.locator("h1")).to_have_text(STORED_NAME)
        expect(head.locator("[data-facts]")).to_contain_text(setup["activity"])
        expect(page.locator("[data-related-tabs]")).to_contain_text("Gegevens")
        expect(page.locator("[data-summary-card]")).to_contain_text("€ 20,00")
        expect(page.locator("#insch-section-answers")).to_contain_text("Braaf")
        assert page.locator("#insch-form").count() == 0, "read first"
        _print(page, "inschrijving-lezen", 1100)
        _print(page, "inschrijving-lezen", 390)
        page.set_viewport_size({"width": 1100, "height": 900})

        head.get_by_role("link", name="Bewerken").click()
        page.locator("#insch-form").wait_for(state="attached")
        _print(page, "inschrijving-bewerken", 1100)
        _print(page, "inschrijving-bewerken", 390)
        page.set_viewport_size({"width": 1100, "height": 900})

        page.fill("#contact_name", "Rik Rechtgezet")
        page.fill(f"#product-{setup['save']}-{setup['product']}", "3")
        page.fill(f"[name=f{setup['story']}]", "Heel braaf")
        with htmx_afgerond(page):
            page.locator("[data-action-bar] [data-form-save]").click()

        # One save: the page is back in read mode with the three changes and the toast.
        expect(page.locator("#insch-form")).to_have_count(0)
        expect(page.locator("[data-record-head] h1")).to_have_text("Rik Rechtgezet")
        expect(page.locator("#insch-section-products")).to_contain_text("3×")
        expect(page.locator("#insch-section-answers")).to_contain_text("Heel braaf")
        expect(page.locator("[data-summary-card]")).to_contain_text("€ 30,00")
    finally:
        page.close()


def test_a_refused_save_keeps_what_was_typed_and_says_why_at_the_field(browser, setup):
    page = _page(browser, setup, 390)
    try:
        page.goto(f"/admin/inschrijvingen/{setup['refuse']}?bewerken=1")
        pagina_klaar(page)
        page.fill("#contact_name", "Nieuwe naam")
        page.fill(f"[name=f{setup['story']}]", "")
        with htmx_afgerond(page):
            page.locator("[data-action-bar] [data-form-save]").click()

        banner = page.locator("#insch-melding [data-save-refusal]")
        expect(banner).to_be_visible()
        assert page.locator(f'[data-error-for="f{setup["story"]}"]').count() == 1
        # What was typed is still there, and nothing was stored.
        assert page.input_value("#contact_name") == "Nieuwe naam"
        page.goto(f"/admin/inschrijvingen/{setup['refuse']}")
        pagina_klaar(page)
        expect(page.locator("[data-record-head] h1")).to_have_text("Weiger Proef")
    finally:
        page.close()


@pytest.mark.parametrize("width", [390, 1100])
@pytest.mark.parametrize("mode", ["read", "edit"])
def test_the_page_does_not_scroll_sideways(browser, setup, width, mode):
    page = _page(browser, setup, width)
    try:
        page.goto(
            f"/admin/inschrijvingen/{setup['refuse']}" + ("?bewerken=1" if mode == "edit" else "")
        )
        pagina_klaar(page)
        scroll = page.evaluate("document.documentElement.scrollWidth")
        wide = page.evaluate(
            """(w) => [...document.querySelectorAll('main *')]
                .filter(e => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().right > w + 1)
                .slice(0, 8).map(e => e.tagName + '.' + String(e.className).slice(0, 50))""",
            width,
        )
        assert scroll == width, f"{mode} @{width}: {scroll} > {width}; {wide}"
    finally:
        page.close()
