"""Reproducible screenshot set for the design track (#785 step 0).

Captures a FIXED set of screens at two widths (admin screens at three, #1482) against a live backend with the
e2e seed — the same environment as the e2e CI job. Two runs on the same commit
must produce the same images; a sha256 manifest is written so that claim can
be checked instead of felt.

Not collected by pytest (no ``test_`` prefix): this is a tool, not a test.

Run, from ``backend/`` with a seeded backend on ``E2E_BASE_URL``::

    python seed_e2e.py                      # once, dev/test only
    python -m tests_e2e.screenshots [outdir]

or via the repo-root wrapper ``./scripts/screenshots.sh [outdir]``.
Default output: ``./screenshots/``. Seed data ONLY — never point this at
UAT or PROD (the admin session is minted locally, so it would not work
there anyway; the rule stands regardless).
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from tests_e2e.schermen import BASE, PLATFORM, login_met_sessie, pagina_klaar

# The audience decides the primary width (CR-08): public screens are judged on
# a phone, admin screens on a desktop. Both widths are captured for every
# screen; the order in the filename makes the primary one sort first.
# CR-11 block 1 (#1482): an admin screen is also judged at 1 920 px, the common
# board desktop (design-system-end-state §1.4), so admin screens get it too.
WIDE = {"width": 1920, "height": 1080}
DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}

# Animations and blinking carets are the enemy of "two runs, same bytes".
FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
}
html { scroll-behavior: auto !important; }
/* The hx-boost progress bar is mid-flight state, not design. */
#nprogress { display: none !important; }
"""


# #1238 punt 2: één taal voor de hele opname. Ze moet op TWEE plaatsen landen en dat is
# gemeten, niet geredeneerd — zie `launch_opties` en `context_opties` hieronder.
TAAL = "nl-BE"


def launch_opties() -> dict:
    """De taal van het BROWSERPROCES (#1238 punt 2).

    Hier staat de helft van de reparatie die niet vanzelf spreekt. Een native
    `<input type="date">` laat Chromium de veldvolgorde kiezen, en Chromium neemt die
    NIET uit de taal van de context maar uit de taal van zijn eigen proces.

    Gemeten op 27 september 2026, met de pijltoets op het geboortedatumveld — die
    verhoogt het eerste segment, dus ze zegt welk segment vooraan staat:

    | opzet | 1955-10-30 + ArrowUp |
    |---|---|
    | kaal | 1955-**11**-30 — de maand staat vooraan |
    | `locale="nl-BE"` op de context | 1955-**11**-30 — onveranderd |
    | `--lang=nl` / `--lang=nl-BE` als argument | 1955-**11**-30 — onveranderd |
    | `LANG=nl_BE.UTF-8` op het proces | 1955-10-**31** — de dag staat vooraan |

    De context-locale alleen zou dus een reparatie zijn die het veld nooit bereikt: op
    de afdruk stond nog `10/30/1955` terwijl `navigator.language` keurig `nl-BE` zei.

    `os.environ` wordt meegenomen: Playwright VERVANGT de omgeving van het
    browserproces met wat hier staat, dus zonder die samenvoeging verliest de browser
    ook `PATH` en `HOME`.
    """
    return {"env": {**os.environ, "LANG": TAAL.replace("-", "_") + ".UTF-8"}}


def context_opties() -> dict:
    """De contextinstellingen van een opname — inclusief de schermafdruk-vlag (#1238).

    De vlag vraagt de schil om de omgevingsbanner niet te renderen: de tool zegt alleen
    *dát* het een opname is, de schil beslist zelf. Het alternatief was een stijlregel
    die de tool injecteert, en dat is een tweede plek die weet hoe die balk eruitziet.

    Ze hangt aan de CONTEXT en niet aan de cookies: `_zet_sessie` wist de cookies vóór
    elk scherm (#1183), dus een cookie was na het eerste scherm weg en de rest van de
    reeks droeg alsnog de banner.

    `locale` (#1238 punt 2) is de tweede helft van de taal: ze zet
    `navigator.language`, de `Accept-Language`-header en de standaardtaal van `Intl` —
    alles wat de PAGINA zelf gebruikt om te formatteren. De veldvolgorde van een
    datumveld komt daar niet uit; die staat in `launch_opties`.

    Een functie en geen letterlijke dict in `main()`, zodat
    `tests_e2e/test_schermafdruk_zonder_banner.py` en
    `tests_e2e/test_schermafdruk_datumvolgorde.py` exact meten wat de tool meestuurt in
    plaats van die waarden na te typen.
    """
    from app.ui import SCREENSHOT_HEADER

    return {
        "reduced_motion": "reduce",
        "locale": TAAL,
        "extra_http_headers": {SCREENSHOT_HEADER: "1"},
    }


@dataclass(frozen=True)
class Screen:
    """One entry of the fixed set."""

    key: str
    path: str
    admin: bool
    # Wie kijkt er mee? (#1183) Tot de ledenflow erbij kwam had de tool één
    # admin-sessie voor de hele reeks — ook op de publieke schermen, waar dat
    # niet opviel. `/aanmelden` is het scherm VÓÓR je aangemeld bent, en het
    # gezinsportaal hoort een gewoon lid te tonen en geen beheerder. De rol zit
    # in de sessiewaarde, niet in de aanmeldfunctie (#718).
    #   None  → geen cookie
    #   "admin" | "lid" | "lid-verlopen" | "lid-vernieuwd" | "lid-overschrijving"
    sessie: Optional[str] = "admin"
    # Runs after navigation, e.g. to open a modal or click through to a
    # seeded record. Receives the page; raises to signal a missing target.
    action: Optional[Callable] = None
    # Koens vraag op het clusterpakket (#996): een full-page-opname mét open
    # modal plakt de hele gedimde pagina onder het venster, waardoor de
    # afbeelding bij passend zoomen sterk verkleint en vaag oogt. Een
    # overlay-scherm knipt daarom alleen de viewport.
    viewport_only: bool = False
    # CR-22 (#1714): runs BEFORE navigation and puts a state in the database
    # that the seed does not hold — a waiting e-mail address, an account, a
    # registration to pay. Not in the seed itself: the measurement baseline
    # and a dozen browser tests read that seed, and a waiting address on the
    # seeded member would move them all. Idempotent, and `main` takes
    # everything staged out again when the set is done; screens that stage
    # stand LAST, so no earlier screen shows what they added.
    stage: Optional[Callable[[], None]] = None


def _open_first_link(page, text: str, url_glob: str) -> None:
    """Navigate to the record behind the first link named ``text``.

    Deliberately goto(href) instead of click(): a click goes through hx-boost,
    whose swap leaves bistable end states (progress bar, focus, swap timing)
    that made these two screens the only irreproducible ones. A full page
    load renders the same target screen the boring, deterministic way.
    """
    link = page.get_by_role("link", name=text).first
    link.wait_for(state="visible", timeout=5000)
    href = link.get_attribute("href")
    if not href:
        raise RuntimeError(f"link {text!r} has no href")
    page.goto(urljoin(page.url, href))  # on the host the list was on (#1535)
    page.wait_for_url(url_glob, timeout=5000)
    page.wait_for_load_state("networkidle")


def _open_registration_page(page) -> None:
    """Open the public registration from the activities list — a page since CR-14
    phase 1 (#1332), a modal before."""
    link = page.locator('a[href*="/inschrijven/"]').first
    link.wait_for(state="visible", timeout=5000)
    link.click()
    # The link is boosted: htmx swaps the body, and the form exists before the swap
    # has settled — a screenshot at that moment caught the activities list halfway
    # through (master CLI on the phase-1 screenshots). Wait for the new URL, Alpine
    # and htmx at rest, and no element still swapping or settling.
    page.wait_for_url("**/inschrijven/**", timeout=5000)
    pagina_klaar(page)
    page.wait_for_function(
        "() => !document.querySelector('.htmx-swapping, .htmx-settling, .htmx-added')",
        timeout=5000,
    )


def _vraag_de_code(page) -> None:
    """Van het e-mailveld naar het codescherm — de tweede stap van aanmelden.

    Een vast adres en geen echt lid: de POST antwoordt altijd hetzelfde, of het
    adres nu gekend is of niet (dat verklapt de route bewust niet), dus het beeld
    hangt niet af van wie er in de seed staat.
    """
    # Uit de seed en niet als letterlijke tekst (#1208): dit adres verscheen hier
    # als tweede kopie naast `MARKER_EMAIL`, terwijl de toelichting bij
    # `_sessiewaarden` hieronder juist zegt dat er één bron is. Een hernoemd
    # seed-gezin liet deze regel anders een leeg aanmeldscherm fotograferen.
    from seed_e2e import MARKER_EMAIL

    page.fill("#email", MARKER_EMAIL)
    page.get_by_role("button", name="Stuur inloginfo").click()
    page.wait_for_selector("#code", timeout=5000)


def _wait_for_the_household_form(page) -> None:
    """The edit mode of Mijn gezin (#1590) is the page's own state (`?bewerken=1`):
    nothing to click, only the form to wait for."""
    page.wait_for_selector("input[id$='-first_name']", timeout=5000)


# ── CR-22 (#1714): what the new screens need that the seed does not hold ────

#: The account of the set: a person without a household. Made up, like the
#: seed's households.
ACCOUNT_EMAIL = "annemieke.vlinder@example.com"
#: The address that waits for its code on the seeded member.
WAITING_EMAIL = "theofiel.nieuw@example.com"
#: The transfer of the staged registration: a structured communication of
#: nobody — its check digits do not hold (they would be 09), as the seed's
#: IBAN carries `00`.
STAGED_OGM = "+++171/4000/00096+++"


def _stage_account() -> None:
    """The account of `ACCOUNT_EMAIL`, as "Account aanmaken" makes one."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import login_person_for_email
    from app.domains.mdm.api import create_account_person

    db = SessionLocal()
    try:
        if login_person_for_email(db, ACCOUNT_EMAIL) is None:
            _person, details = create_account_person(
                db,
                first_name="Annemieke",
                last_name="Vlinder",
                email=ACCOUNT_EMAIL,
                mobile="0470 00 00 22",
            )
            db.add_all(details)
            db.commit()
    finally:
        db.close()


def _stage_waiting_address() -> None:
    """An address the seeded member typed himself, waiting for its code."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import login_person_for_email
    from app.domains.mdm.api import ContactDetail, new_contact_detail
    from seed_e2e import MARKER_EMAIL

    db = SessionLocal()
    try:
        if db.query(ContactDetail).filter(ContactDetail.value == WAITING_EMAIL).first() is None:
            person = login_person_for_email(db, MARKER_EMAIL)
            db.add(
                new_contact_detail(
                    db, person, "EMAIL", WAITING_EMAIL, is_primary=False, confirmed=False
                )
            )
            db.commit()
    finally:
        db.close()


def _stage_registration() -> None:
    """The seeded member's own registration for the seeded activity, with a
    transfer still to make — what Mijn Raak and Mijn inschrijvingen show."""
    from decimal import Decimal

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, Registration, RegistrationItem
    from app.domains.auth.api import login_person_for_email
    from app.domains.payment.api import PaymentRecord
    from seed_e2e import MARKER_EMAIL

    db = SessionLocal()
    try:
        if db.query(PaymentRecord).filter_by(structured_communication=STAGED_OGM).first():
            return
        person = login_person_for_email(db, MARKER_EMAIL)
        activity = db.query(Activity).filter(Activity.name == "E2E-activiteit").one()
        component = activity.sub_registrations[0]
        registration = Registration(
            activity_id=activity.id,
            component_id=component.id,
            person_id=person.id,
            registration_type="INDIVIDUAL",
            contact_name=f"{person.first_name} {person.last_name}",
            contact_email=MARKER_EMAIL,
            phone="0470 00 00 01",
        )
        db.add(registration)
        db.flush()
        db.add(
            RegistrationItem(
                registration_id=registration.id, product_id=component.products[0].id, quantity=3
            )
        )
        db.add(
            PaymentRecord(
                payable_type="registration",
                payable_id=registration.id,
                amount=Decimal("30.00"),
                method="transfer",
                status="pending",
                structured_communication=STAGED_OGM,
            )
        )
        db.commit()
    finally:
        db.close()


def _unstage() -> None:
    """Take out what the three functions above put in: the next run, and any
    browser test on this database, finds the seed as it was."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Registration, RegistrationItem
    from app.domains.mdm.api import ContactDetail, Person
    from app.domains.payment.api import PaymentRecord
    from app.soft_delete import soft_delete

    db = SessionLocal()
    try:
        for booking in db.query(PaymentRecord).filter_by(structured_communication=STAGED_OGM):
            db.query(RegistrationItem).filter_by(registration_id=booking.payable_id).delete()
            db.query(Registration).filter_by(id=booking.payable_id).delete()
            db.delete(booking)
        for contact in db.query(ContactDetail).filter(ContactDetail.value == WAITING_EMAIL):
            soft_delete(contact)
        for contact in db.query(ContactDetail).filter(ContactDetail.value == ACCOUNT_EMAIL).all():
            person = db.query(Person).filter(Person.id == contact.person_id).first()
            if person is not None:
                for other in person.contact_details:
                    soft_delete(other)
                soft_delete(person)
        db.commit()
    finally:
        db.close()


def _ask_the_account_code(page) -> None:
    """From the four fields of "Account aanmaken" to its code step. A fixed
    address that is nobody's: the step answers the same for every address."""
    form = page.locator("[data-create-account-form]")
    form.locator('input[name="first_name"]').fill("Annemieke")
    form.locator('input[name="last_name"]').fill("Vlinder")
    form.locator('input[name="email"]').fill("annemieke.nieuw@example.com")
    form.locator('input[name="mobile"]').fill("0470 00 00 22")
    form.locator("button").click()
    page.wait_for_selector("#code", timeout=5000)


def _open_the_code_page(page) -> None:
    """ "Code invoeren" under the waiting address. A full load of the link's
    address, for the reason `_open_first_link` gives."""
    link = page.locator("[data-enter-code]").first
    link.wait_for(state="visible", timeout=5000)
    page.goto(urljoin(page.url, link.get_attribute("href")))
    page.wait_for_selector("#code", timeout=5000)


SCREENS: tuple[Screen, ...] = (
    # Public — judged phone-first.
    Screen("public-home", "/", admin=False),
    Screen("public-activiteiten", "/activiteiten", admin=False),
    Screen(
        "public-inschrijfmodal",
        "/activiteiten",
        admin=False,
        viewport_only=True,
        action=_open_registration_page,
    ),
    Screen("public-word-lid", "/lid-worden", admin=False),
    Screen("public-formulier", "/formulier/tok-e2e-open", admin=False),
    # Admin — judged desktop-first.
    Screen("admin-dashboard", "/admin", admin=True),
    Screen("admin-betalingen", "/admin/betalingen", admin=True),
    Screen("admin-leden", "/admin/leden", admin=True),
    Screen(
        "admin-activiteit-detail",
        "/admin/activiteiten",
        admin=True,
        # `/**` and not `/*` (#1714): since #1557 the link carries
        # `?terug=/admin/activiteiten`, and `*` stops at a slash — this screen
        # was missing from every set since.
        action=lambda page: _open_first_link(page, "E2E-activiteit", "**/admin/activiteiten/**"),
    ),
    Screen(
        "admin-formulierbouwer",
        "/admin/formulieren",
        admin=True,
        action=lambda page: _open_first_link(page, "E2E-formulier", "**/admin/formulieren/*"),
    ),
    # The living component kit — review-round material.
    Screen("admin-design-system", "/admin/design-system", admin=True),
    # CR-19 (#1478, Q1): the company tenant of the seed — its editor with the
    # kind and the reduced module set, and the site it starts with.
    Screen(
        "admin-tenant-bedrijf",
        PLATFORM + "/admin/tenants",  # #1535: platform administration
        admin=True,
        action=lambda page: _open_first_link(page, "Voorbeeldbedrijf", "**/admin/tenants/*"),
    ),
    Screen("bedrijf-home", "/voorbeeldbedrijf/", admin=False),
    # Ledenflow (#1183) — het beeldmateriaal voor de publieke uitlegpagina over
    # aanmelden, je gegevens nakijken en je lidmaatschap verlengen. Telefoon-eerst,
    # want zo'n pagina wordt vooral op een telefoon gelezen.
    #
    # Uit de SEED en niet met de hand: HDEV draagt echte ledenrecords, dus een
    # afdruk van het gezinsscherm daar zet naam en adres van een echt lid op een
    # publieke pagina — een lek dat geen grep vindt, want het zit in een afbeelding.
    Screen("leden-aanmelden", "/aanmelden", admin=False, sessie=None),
    Screen("leden-aanmelden-code", "/aanmelden", admin=False, sessie=None, action=_vraag_de_code),
    Screen("leden-gezin", "/leden/gezin", admin=False, sessie="lid"),
    Screen(
        "leden-gezin-bewerken",
        "/leden/gezin?bewerken=1",
        admin=False,
        sessie="lid",
        action=_wait_for_the_household_form,
    ),
    # Een toestand die het seed-gezin niet kán tonen, met een eigen gezin: het
    # lopende lidmaatschap verbergt de vernieuwknop.
    #
    # Het scherm met de BETAALINSTRUCTIES (bedrag, IBAN, OGM) ontbreekt bewust. Het
    # bestaat alleen bij een vernieuwing die al loopt, en zo'n openstaande betaling
    # in de gedeelde seed is precies de rij die `test_beheer_flows` als eerste
    # "Bevestig" oppikt — gemeten: die test zette hem op betaald, waarna het scherm
    # verdween én die test iets anders toetste dan bedoeld. Het was in #1183 een
    # "als het kan"-punt; dit is de reden dat het niet kan zonder dat elders te
    # verstoren.
    # #1590: renewing is its own page; Mijn gezin only links to it.
    Screen("leden-verlengen", "/leden/gezin/vernieuwen", admin=False, sessie="lid-verlopen"),
    # Verlengflow (#1241): twee toestanden die een ander gezin niet kán tonen, elk met
    # een eigen gezin in de seed.
    #
    # "Je kan verlengen" heeft GEEN eigen ingang: sinds #1238 punt 5 staat het
    # hernieuwingsvenster open in deze omgeving, dus `leden-gezin` hierboven ís dat
    # scherm. Een tweede afdruk die hetzelfde toont met een ander gezin erop zou een
    # tweede plek voor één feit zijn — en lopen die twee ooit uit elkaar, dan weet
    # niemand welke de uitlegpagina hoort te gebruiken.
    Screen("leden-verlengen-online-gelukt", "/leden/gezin", admin=False, sessie="lid-vernieuwd"),
    Screen(
        "leden-verlengen-overschrijving",
        "/leden/gezin/vernieuwen",
        admin=False,
        sessie="lid-overschrijving",
    ),
    # CR-22 (#1714): the screens of signing in with an account. `leden-aanmelden`
    # above is the sign-in screen with the link "Account aanmaken" since #1708.
    # Phone-first, like the member flow. The screens that `stage` stand last —
    # see `Screen.stage`.
    Screen("account-aanmaken", "/account-aanmaken", admin=False, sessie=None),
    Screen(
        "account-aanmaken-code",
        "/account-aanmaken",
        admin=False,
        sessie=None,
        action=_ask_the_account_code,
    ),
    Screen("mijn-gegevens", "/mijn/gegevens", admin=False, sessie="lid"),
    Screen("mijn-raak-lid", "/mijn", admin=False, sessie="lid", stage=_stage_registration),
    Screen(
        "mijn-inschrijvingen",
        "/mijn/inschrijvingen",
        admin=False,
        sessie="lid",
        stage=_stage_registration,
    ),
    Screen("mijn-raak-account", "/mijn", admin=False, sessie="account", stage=_stage_account),
    Screen(
        "mijn-gegevens-account",
        "/mijn/gegevens",
        admin=False,
        sessie="account",
        stage=_stage_account,
    ),
    Screen(
        "mijn-gezin-wachtend-adres",
        "/leden/gezin",
        admin=False,
        sessie="lid",
        stage=_stage_waiting_address,
    ),
    Screen(
        "mijn-gegevens-wachtend-adres",
        "/mijn/gegevens",
        admin=False,
        sessie="lid",
        stage=_stage_waiting_address,
    ),
    Screen(
        "adres-bevestigen-code",
        "/mijn/gegevens",
        admin=False,
        sessie="lid",
        stage=_stage_waiting_address,
        action=_open_the_code_page,
    ),
)


def _sessiewaarden() -> dict[str, str]:
    """Eén sessiewaarde per rol die de reeks nodig heeft (#1183).

    De ledenadressen komen uit `seed_e2e` en niet uit een lijstje hier: één bron,
    zodat een hernoemd seed-gezin deze tool meteen laat struikelen in plaats van
    stilletjes een leeg scherm te fotograferen.
    """
    from app.domains.auth.api import make_session_value
    from seed_e2e import (
        MARKER_EMAIL,
        MARKER_EMAIL_OVERSCHRIJVING,
        MARKER_EMAIL_VERLOPEN,
        MARKER_EMAIL_VERNIEUWD,
    )

    admin = os.environ.get("E2E_ADMIN_EMAIL")
    if not admin:
        from tests.conftest import SEEDED_ADMIN_EMAIL

        admin = SEEDED_ADMIN_EMAIL
    return {
        "admin": make_session_value(admin),
        "lid": make_session_value(MARKER_EMAIL),
        "lid-verlopen": make_session_value(MARKER_EMAIL_VERLOPEN),
        "lid-vernieuwd": make_session_value(MARKER_EMAIL_VERNIEUWD),
        "lid-overschrijving": make_session_value(MARKER_EMAIL_OVERSCHRIJVING),
        # CR-22 (#1714): a person without a household, staged by its screens.
        "account": make_session_value(ACCOUNT_EMAIL),
    }


def _zet_sessie(page, waarde: Optional[str]) -> None:
    """De cookie voor dit scherm — eerst wissen, dan zetten (#1183).

    Wissen hoort erbij: zonder dat draagt `/aanmelden` nog de sessie van het
    vorige scherm en fotografeer je een aangemelde bezoeker op het aanmeldscherm.
    """
    page.context.clear_cookies()
    if waarde:
        login_met_sessie(page, waarde)
        login_met_sessie(page, waarde, PLATFORM)  # #1535: the platform screens


def _capture(page, screen: Screen, width: dict, out_dir: Path) -> Path:
    page.set_viewport_size(width)
    if screen.stage:
        screen.stage()
    page.goto(screen.path)
    page.wait_for_load_state("networkidle")
    if screen.action:
        screen.action(page)
    page.add_style_tag(content=FREEZE_CSS)
    # Webfonts shift every line height when they land late — one run rendered
    # the builder in the fallback font and nothing hashed the same. fonts.ready
    # alone resolves trivially when the face was not requested yet, so load the
    # families explicitly before waiting.
    page.evaluate(
        """Promise.all([
             document.fonts.load('1em Inter'),
             document.fonts.load('700 1em Inter'),
             document.fonts.load('1em "Radio Canada Big"'),
           ]).then(() => document.fonts.ready).then(() => null)"""
    )
    # #997: until no htmx swap is still running or settling, instead of one
    # guessed "settle beat". Without htmx on the page there is nothing to wait for.
    page.wait_for_function(
        "() => !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')"
    )
    name = f"{screen.key}-{width['width']}.png"
    target = out_dir / name
    page.screenshot(path=str(target), full_page=not screen.viewport_only)
    return target


def main(argv: list[str]) -> int:
    # Hard stop, not a docstring: against HDEV/UAT/PROD these images would show
    # real members and addresses. Localhost is the only target this tool has.
    from urllib.parse import urlparse

    host = urlparse(BASE).hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        print(
            f"refused: E2E_BASE_URL points at {host!r} — this tool captures "
            "seeded LOCAL screens only, never a live environment.",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(argv[1]) if len(argv) > 1 else Path("screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    sessies = _sessiewaarden()
    captured: list[Path] = []
    missing: list[str] = []

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        opstart = dict(launch_opties())
        if exe:
            opstart["executable_path"] = exe
        browser = pw.chromium.launch(**opstart)
        context = browser.new_context(base_url=BASE, **context_opties())
        page = context.new_page()

        for screen in SCREENS:
            if screen.sessie is not None and screen.sessie not in sessies:
                missing.append(f"{screen.key}: onbekende sessie {screen.sessie!r}")
                continue
            # Primary width first: phone for public, desktop for admin; an admin
            # screen also at 1 920 (#1482).
            widths = (WIDE, DESKTOP, PHONE) if screen.admin else (PHONE, DESKTOP)
            for width in widths:
                try:
                    _zet_sessie(page, sessies.get(screen.sessie) if screen.sessie else None)
                    captured.append(_capture(page, screen, width, out_dir))
                except Exception as exc:  # noqa: BLE001 - report, don't die mid-set
                    missing.append(f"{screen.key} @ {width['width']}: {exc}")
        browser.close()
    if any(screen.stage for screen in SCREENS):
        _unstage()

    manifest = out_dir / "manifest.txt"
    lines = []
    for path in sorted(captured):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{len(captured)} screenshots -> {out_dir}/ (manifest: {manifest.name})")
    if missing:
        # The #644 lesson: with the seed loaded, a missing screen is a
        # finding, not a footnote.
        for entry in missing:
            print(f"MISSING: {entry}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
