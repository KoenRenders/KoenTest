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


# ── CR-22 (S9, #1714): one golden flow per door ──────────────────────────────
#
# Three ways in since CR-22 (R1): make an account, register as a guest, sign in
# as a member. Each flow below walks one door from the public site to what the
# visitor ends up with — the pieces have their own tests (`test_create_account`,
# `test_my_registrations`, `test_my_details`, `test_confirm_address`,
# `test_account_shell`); these hold that the pieces still form ONE road.
#
# **Each door comes from its own address.** The sign-in routes are limited to
# five sends a minute per IP (`login_limiter`) and the whole e2e run is one IP:
# in the full run the first send of these flows was refused with a 429, spent
# by the tests before them, while the file alone was green. The limiter reads
# the last address of `X-Forwarded-For` (behind the proxy, the proxy writes
# it); here nothing stands in front of the backend, so a door names its own —
# from the range reserved for documentation — and shares no counter.
#
# **By the link of the mail, not the code.** The link does what the code does
# (CR-22 Q36), and no other browser test follows it; typing the code has its
# own tests (`test_create_account`, `test_sign_in_returns_to_the_portal`).
#
# Broken on purpose (8 October 2026), each red for its own reason: the mail's
# link forgetting the page that asked → the account and the member land on
# Mijn Raak instead; an account given the household's menu → the account's
# menu has a fourth page; Mijn inschrijvingen showing every registration → the
# guest's stands under somebody's account; the hint shown to whoever is signed
# in → it stands above a signed-in form.


def _door(page, number: int, width: int = 390):
    """A visitor of their own: a fresh context (no cookie of another flow), at
    the width most visitors have, from an address of their own (`number`)."""
    context = page.context.browser.new_context(
        base_url=BASE,
        viewport={"width": width, "height": 844},
        extra_http_headers={"X-Forwarded-For": f"198.51.100.{number}"},
    )
    return context.new_page()


def _mail_link(email: str, back: str = "") -> str:
    """The link of the mail that was just sent to this address, as `auth.login`
    writes it: the living token, and the page that asked."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import LoginToken

    db = SessionLocal()
    try:
        token = (
            db.query(LoginToken)
            .filter(LoginToken.email == email, LoginToken.used.is_(False))
            .order_by(LoginToken.id.desc())
            .first()
        )
        assert token is not None, f"no code was sent to {email}"
        return f"/login/verify?token={token.token}" + (f"&terug={back}" if back else "")
    finally:
        db.close()


def _forget(email: str) -> None:
    """Take the person this flow made out again: the list of persons without a
    household is another test's (`test_persons`)."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import ContactDetail, Person
    from app.soft_delete import soft_delete

    db = SessionLocal()
    try:
        for contact in db.query(ContactDetail).filter(ContactDetail.value == email).all():
            person = db.query(Person).filter(Person.id == contact.person_id).first()
            if person is not None:
                for other in person.contact_details:
                    soft_delete(other)
                soft_delete(person)
        db.commit()
    finally:
        db.close()


def _menu(page) -> list[str]:
    """Where the account menu leads, in its order (hidden on a phone, where
    the drawer carries it — the links are the same)."""
    return page.locator("[data-account-page-menu] a").evaluate_all(
        "links => links.map(a => a.getAttribute('href'))"
    )


def _register(page, aid: int, cid: int, *, name: str, email: str, team: str) -> None:
    """Send the registration form of the team component, as whoever is on it."""
    page.fill("#contact_name", name)
    page.fill("#contact_email", email)
    page.fill("#phone", "0470000000")
    page.fill("#team_name", team)
    page.locator("#inschrijf-pagina button[type=submit]").click()
    expect(page.get_by_text("Je inschrijving is ontvangen")).to_be_visible()


def _my_registrations(page) -> list[str]:
    page.goto("/mijn/inschrijvingen")
    expect(page.locator("[data-page-title]")).to_have_text("Mijn inschrijvingen")
    return [t.strip() for t in page.locator("[data-my-registration] h2").all_inner_texts()]


def test_door_account_from_an_activity_to_mijn_inschrijvingen(page, seeded_activities):
    """Door 1 (CR-22 W1, R1, R3, R13, R15): somebody who is no member registers
    WITH an account. From the activity's form to "Account aanmaken", the mail's
    link back to that same form, the registration, and it stands under Mijn
    inschrijvingen — on Mijn Raak without anything of a household."""
    aid, cid = seeded_activities["team"]
    email = f"e2e-account-{int(time.time() * 1000)}@example.com"
    form_path = f"/activiteiten/{aid}/inschrijven/{cid}"
    door = _door(page, 1)
    try:
        open_registration(door, aid, cid)
        sign_in = door.locator("[data-member-nudge] a").get_attribute("href")
        assert sign_in == f"/aanmelden?terug={form_path}", sign_in
        door.goto(sign_in)
        create = door.locator("[data-create-account] a").get_attribute("href")
        assert create == f"/account-aanmaken?terug={form_path}", create
        door.goto(create)

        form = door.locator("[data-create-account-form]")
        form.locator('input[name="first_name"]').fill("Dora")
        form.locator('input[name="last_name"]').fill("Deurproef")
        form.locator('input[name="email"]').fill(email)
        form.locator('input[name="mobile"]').fill("0470 00 17 14")
        form.locator("button").click()
        expect(door.locator("[data-code-sent]")).to_be_visible()

        # The link of "Bevestig je account": it makes the account, signs in and
        # comes back to the form that asked (the page wins over the landing).
        door.goto(_mail_link(email, form_path))
        door.wait_for_url(f"**{form_path}")
        expect(door.locator("[data-member-nudge]")).to_have_count(0)
        _register(door, aid, cid, name="Dora Deurproef", email=email, team="De Deurzoekers")

        assert _my_registrations(door) == ["E2E Ploegenspel"]
        # Mijn Raak for an account: its own data and its registrations, no household.
        assert _menu(door) == ["/mijn", "/mijn/gegevens", "/mijn/inschrijvingen"], _menu(door)
        door.goto("/mijn/gegevens?bewerken=1")
        names = door.locator("#gegevens-form input:not([type=hidden])").evaluate_all(
            "inputs => inputs.map(i => i.name.split('.').pop())"
        )
        assert names == ["first_name", "last_name", "mobile", "value"], names
        expect(door.locator('#gegevens-form input[type="email"]')).to_have_value(email)
    finally:
        door.context.close()
        _forget(email)


def test_door_guest_registers_and_it_is_nobodys_history(page, seeded_activities):
    """Door 2 (CR-22 W2, R5, R23): a guest registers as before, under the hint
    that names the other two doors. The registration belongs to no account:
    somebody who later has an account on that same address does not find it
    under Mijn inschrijvingen — the address was typed, never proven."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.mdm.api import create_account_person
    from tests_e2e.schermen import login_met_sessie

    aid, cid = seeded_activities["team"]
    email = f"e2e-gast-{int(time.time() * 1000)}@example.com"
    door = _door(page, 2)
    try:
        open_registration(door, aid, cid)
        expect(door.locator("[data-member-nudge]")).to_have_text(
            "Heb je een account of ben je lid? Log je eerst aan."
        )
        _register(door, aid, cid, name="Gust Gastproef", email=email, team="De Gasten")

        db = SessionLocal()
        try:
            _person, details = create_account_person(
                db, first_name="Gust", last_name="Gastproef", email=email, mobile="0470001714"
            )
            db.add_all(details)
            db.commit()
        finally:
            db.close()
        login_met_sessie(door, make_session_value(email), BASE)
        assert _my_registrations(door) == [], "a guest's registration became somebody's history"
    finally:
        door.context.close()
        _forget(email)


def test_door_member_signs_in_from_the_page_that_asked(page, seeded_activities):
    """Door 3 (CR-22 W3, R2, R13–R15): a member opens the renewal link signed
    out, signs in, and arrives on the renewal page — not on Mijn Raak. Mijn
    Raak has the household beside the two pages an account has; a registration
    made signed in stands under Mijn inschrijvingen; and on a phone the drawer
    reaches every page of the menu."""
    from seed_e2e import MARKER_EMAIL_VERLOPEN

    aid, cid = seeded_activities["team"]
    renew = "/leden/gezin/vernieuwen"
    door = _door(page, 3)
    try:
        door.goto(renew)
        door.wait_for_url(f"**/aanmelden?terug={renew}")
        door.fill("#email", MARKER_EMAIL_VERLOPEN)
        door.get_by_role("button", name="Stuur inloginfo").click()
        door.wait_for_selector("#code")
        door.goto(_mail_link(MARKER_EMAIL_VERLOPEN, renew))
        door.wait_for_url(f"**{renew}")

        door.goto("/mijn")
        pages = ["/mijn", "/mijn/gegevens", "/leden/gezin", "/mijn/inschrijvingen"]
        assert _menu(door) == pages, _menu(door)

        team = f"De Leden {int(time.time())}"
        open_registration(door, aid, cid)
        expect(door.locator("[data-member-nudge]")).to_have_count(0)
        _register(door, aid, cid, name="Lid Deurproef", email=MARKER_EMAIL_VERLOPEN, team=team)
        assert "E2E Ploegenspel" in _my_registrations(door)

        # On a phone the menu is the drawer's (R14): every page, from any page.
        door.locator("[data-menu-button]").click()
        drawer = door.locator("[data-drawer-account] a").evaluate_all(
            "links => links.map(a => a.getAttribute('href'))"
        )
        assert [href for href in pages if href in drawer] == pages, drawer
    finally:
        door.context.close()
