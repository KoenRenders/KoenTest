"""E2E golden flows (React-exit 405-e, #405) — playwright-python tegen de
server-rendered site (geen Node meer).

Draait NIET in de gewone pytest-suite (testpaths=tests): vereist een live
backend op E2E_BASE_URL (default http://localhost:8000) met gemigreerde DB en
geseede postcodes. CI start uvicorn en draait `pytest tests_e2e`.
"""

import os
import sys
import time

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import fill_signup, open_registration, send_form  # noqa: E402

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        # E2E_CHROMIUM_PATH: gebruik een vooraf geïnstalleerde Chromium (bv. in
        # een sandbox) i.p.v. de door `playwright install` beheerde download.
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        yield page
        browser.close()


def test_gezinsregistratie_met_overschrijving(page):
    """Kernflow (#128): gezinsregistratie via Word lid met betaaltype
    overschrijving — raakt Mollie niet, dus stabiel zonder gateway-stub.

    #1590: the page stands on the public form page; its one button is the
    action bar's, and the confirmation says "Je aanvraag is ontvangen"."""
    page.goto("/lid-worden")
    fill_signup(page, f"e2e+{int(time.time())}@example.com")
    page.check('input[name="payment_method"][value="transfer"]')
    send_form(page)
    expect(page.get_by_role("heading", name="Je aanvraag is ontvangen")).to_be_visible()


def test_gezinsregistratie_zonder_postcode_geblokkeerd(page):
    """#160: without a chosen postal code nothing is created.

    #1590: the browser no longer blocks the submit (`novalidate`, so the message
    is always the kit's): the server refuses, the banner names the field and the
    select is marked — and the page keeps what was typed."""
    page.goto("/lid-worden")
    fill_signup(page, "nopc@example.com", postal_code=False)
    send_form(page)
    expect(page.locator("[data-save-refusal]")).to_contain_text("Verzenden kan nog niet")
    expect(page.locator('[data-field="address.postal_code"]')).to_have_attribute("data-refused", "")
    expect(page.locator("#address-postal_code")).to_be_focused()
    expect(page.locator("#address-street")).to_have_value("Teststraat")
    expect(page.get_by_role("heading", name="Je aanvraag is ontvangen")).to_have_count(0)


@pytest.fixture(scope="module")
def seeded_activities():
    """Maakt via de DB (zelfde DATABASE_URL als de live backend) een open
    activiteit met een ploegnaam-onderdeel en één met een betalend product.
    De tenant-default (Millegem) matcht de host-resolutie op localhost, dus de
    activiteiten verschijnen op de publieke site."""
    from datetime import date, timedelta
    from decimal import Decimal

    import app.models  # noqa: F401  triggert load_all_models() → alle mappers geconfigureerd
    from app.database import SessionLocal
    from app.domains.activities.api import (
        Activity,
        ActivityDate,
        ActivityProduct,
        ActivitySubRegistration,
    )

    db = SessionLocal()
    toekomst = date.today() + timedelta(days=30)

    team = Activity(name="E2E Ploegenspel")
    db.add(team)
    db.flush()
    db.add(ActivityDate(activity_id=team.id, start_date=toekomst))
    team_comp = ActivitySubRegistration(
        activity_id=team.id,
        name="Ploegonderdeel",
        team_name_required=True,
        price=Decimal("0"),
        is_free=True,
    )
    db.add(team_comp)
    db.flush()

    prod_act = Activity(name="E2E Productenspel")
    db.add(prod_act)
    db.flush()
    db.add(ActivityDate(activity_id=prod_act.id, start_date=toekomst))
    prod_comp = ActivitySubRegistration(
        activity_id=prod_act.id, name="Producten", price=Decimal("0"), is_free=True
    )
    db.add(prod_comp)
    db.flush()
    ticket = ActivityProduct(
        component_id=prod_comp.id, name="Ticket", price=Decimal("10.00"), is_free=False
    )
    db.add(ticket)
    db.flush()

    db.commit()
    ids = {"team": (team.id, team_comp.id), "prod": (prod_act.id, prod_comp.id, ticket.id)}
    db.close()
    return ids


def _open_inschrijfform(page, aid: int, cid: int):
    open_registration(page, aid, cid)
    page.fill("#contact_name", "E2E Deelnemer")
    page.fill("#contact_email", f"e2e+{int(time.time() * 1000)}@example.com")
    page.fill("#phone", "0470000000")


def test_activiteit_inschrijving_met_ploegnaam(page, seeded_activities):
    """Golden flow: publieke inschrijving voor een activiteit met een ploegnaam
    (TEAM-onderdeel) — geen betaling."""
    aid, cid = seeded_activities["team"]
    _open_inschrijfform(page, aid, cid)
    page.fill("#team_name", "De Kampioenen")
    page.locator("#inschrijf-pagina button[type=submit]").click()
    expect(page.get_by_text("Je inschrijving is ontvangen")).to_be_visible()
    # P8 and P10 (CR-14 B4.9): the thank-you page leads back to the activity, where
    # the list of this component is open and already names the new registration —
    # the in-place refresh of the modal (#1159) became a refresh on return.
    page.get_by_role("link", name="Terug naar de activiteit").click()
    page.wait_for_url(f"**/activiteiten/*?deelnemers={cid}")
    expect(page.locator(f"#deelnemers-{aid}-{cid}")).to_contain_text("De Kampioenen")


def test_activiteit_inschrijving_met_producten_en_betaling(page, seeded_activities):
    """Golden flow: publieke inschrijving voor een activiteit met een betalend
    product + een betaling (overschrijving — stabiel, raakt Mollie niet)."""
    aid, cid, pid = seeded_activities["prod"]
    _open_inschrijfform(page, aid, cid)
    page.fill(f'input[name="product_{pid}"]', "2")
    # CR-12 phase 1: the radio value is the code, not the Dutch word.
    page.check('input[name="payment_method"][value="transfer"]')
    page.locator("#inschrijf-pagina button[type=submit]").click()
    expect(page.get_by_text("Je inschrijving is ontvangen")).to_be_visible()


@pytest.fixture(scope="module")
def wizard_form_token():
    """Een open meersectie-formulier (3 secties, geen losse velden) → de wizard
    is actief. Voor de stap-per-stap-navigatietest (#480)."""
    import secrets

    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.forms.models import Form, FormField, FormSection

    db = SessionLocal()
    token = "e2e-" + secrets.token_urlsafe(8)
    form = Form(title="E2E Enquête", status="open", is_anonymous=True, share_token=token)
    db.add(form)
    db.flush()
    for i in range(3):
        sec = FormSection(form_id=form.id, title=f"Sectie {i + 1}", position=i)
        db.add(sec)
        db.flush()
        db.add(
            FormField(
                form_id=form.id,
                section_id=sec.id,
                field_type="text",
                label=f"Vraag {i + 1}",
                position=0,
            )
        )
    db.commit()
    db.close()
    return token


def test_formulier_wizard_navigatie(page, wizard_form_token):
    """Golden flow (#480), as it is since #1589 (CR-11 pilot B): a form of
    several sections is ONE page. Every section is a card on it, there is no
    'Vorige' or 'Volgende', and 'Verzenden' stands in the bar from the start.
    (The name of this test is kept: it is the golden flow of that form.)"""
    page.goto(f"/formulier/{wizard_form_token}")
    expect(page.get_by_role("button", name="Verzenden")).to_be_visible()
    expect(page.get_by_role("button", name="Vorige")).to_have_count(0)
    expect(page.get_by_role("button", name="Volgende")).to_have_count(0)
    cards = page.locator("[data-question-cards] [data-form-section]")
    assert cards.count() >= 3, "the sections are not all on the page"
    for index in range(cards.count()):
        expect(cards.nth(index)).to_be_visible()


def test_publieke_kern_bereikbaar(page):
    """Smoke: de publieke kernpagina's renderen server-side."""
    for pad, tekst in (
        ("/", "Raak"),
        ("/activiteiten", "Activiteiten"),
        ("/fotos", "Foto's"),
        ("/berichten", ""),
    ):
        resp = page.goto(pad)
        assert resp is not None and resp.ok, pad
        if tekst:
            expect(page.get_by_text(tekst).first).to_be_visible()
