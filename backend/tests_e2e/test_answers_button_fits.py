"""E2E #1382: the button "Antwoorden" fits the row of its component at 390 px.

"Antwoorden" is longer than "Boek". Measured on the rendered registrations overview,
with a long component name: the button stays inside its component's card, and the
card inside the screen.

Proven red against master `08a3ffbd` with the new word (30 September 2026): at
390 px the button ended at 429 px in a card ending at 374 — the group's header row
did not wrap. 1280 px fitted.

Not measured here, on purpose: the page as a whole is 682 px wide at 390, because
the activity's record header (`_aa_recordkop.html`) keeps its buttons next to the
title with `shrink-0`. That predates #1382 and holds on every tab; it is reported
on its own, not folded into this issue.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def setup():
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities import service
    from app.domains.auth.api import make_session_value
    from app.schemas.activity import RegistrationCreate
    from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product, seed_question_form

    db = SessionLocal()
    activity, component, product = seed_activity_with_product(db, price="0", is_free=True)
    component.name = "Bezoek aan huis in de voormiddag"
    db.commit()
    form = seed_question_form(db)
    service.update_component(db, activity.id, component.id, {"form_id": form.id})
    data = RegistrationCreate(
        contact_name="Rij Proef",
        contact_email="rij@example.com",
        phone="0470000000",
        component_id=component.id,
        items=[{"product_id": product.id, "quantity": 1}],
    )
    service.register(db, activity, data, person_id=None, actor="e2e")
    db.commit()
    out = {"activity": activity.id, "session": make_session_value(SEEDED_ADMIN_EMAIL)}
    db.close()
    return out


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_the_answers_button_stays_in_its_card(browser, setup, width):
    context = browser.new_context(base_url=BASE, viewport={"width": width, "height": 900})
    page = context.new_page()
    try:
        login_met_sessie(page, setup["session"])
        page.goto(f"/admin/activiteiten/{setup['activity']}/inschrijvingen")
        pagina_klaar(page)
        m = page.evaluate(
            """() => { const a = [...document.querySelectorAll('a')]
                 .find(x => x.innerText.trim() === 'Antwoorden');
               if (!a) return null;
               const r = a.getBoundingClientRect(), c = a.closest('.rounded-2xl').getBoundingClientRect();
               return {btn: [Math.round(r.left), Math.round(r.right)],
                       card: [Math.round(c.left), Math.round(c.right)], vw: innerWidth}; }"""
        )
        assert m is not None, "no button Antwoorden on the overview"
        assert m["card"][0] <= m["btn"][0] and m["btn"][1] <= m["card"][1], m
        assert m["card"][1] <= m["vw"], m
    finally:
        context.close()
