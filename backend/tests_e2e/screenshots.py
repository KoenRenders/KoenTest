"""Reproducible screenshot set for the design track (#785 step 0).

Captures a FIXED set of screens at two widths against a live backend with the
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

from playwright.sync_api import sync_playwright

from tests_e2e.schermen import BASE, login_met_sessie

# The audience decides the primary width (CR-08): public screens are judged on
# a phone, admin screens on a desktop. Both widths are captured for every
# screen; the order in the filename makes the primary one sort first.
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
    #   "admin" | "lid" | "lid-verlopen"
    sessie: Optional[str] = "admin"
    # Runs after navigation, e.g. to open a modal or click through to a
    # seeded record. Receives the page; raises to signal a missing target.
    action: Optional[Callable] = None
    # Koens vraag op het clusterpakket (#996): een full-page-opname mét open
    # modal plakt de hele gedimde pagina onder het venster, waardoor de
    # afbeelding bij passend zoomen sterk verkleint en vaag oogt. Een
    # overlay-scherm knipt daarom alleen de viewport.
    viewport_only: bool = False


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
    page.goto(href)
    page.wait_for_url(url_glob, timeout=5000)
    page.wait_for_load_state("networkidle")


def _open_register_modal(page) -> None:
    """Open the public registration modal on the activities list."""
    button = page.get_by_role("button", name="Inschrijven").first
    button.wait_for(state="visible", timeout=5000)
    button.click()
    # The htmx swap fills an #inschrijf-* container; wait for the form.
    page.wait_for_selector("form >> text=Inschrijven", timeout=5000)


def _vraag_de_code(page) -> None:
    """Van het e-mailveld naar het codescherm — de tweede stap van aanmelden.

    Een vast adres en geen echt lid: de POST antwoordt altijd hetzelfde, of het
    adres nu gekend is of niet (dat verklapt de route bewust niet), dus het beeld
    hangt niet af van wie er in de seed staat.
    """
    page.fill("#email", "e2e-seed@example.com")
    page.get_by_role("button", name="Stuur inloginfo").click()
    page.wait_for_selector("#code", timeout=5000)


def _bewerk_eerste_gezinslid(page) -> None:
    """Klap de bewerkvorm van het eerste gezinslid open."""
    knop = page.get_by_role("button", name="Bewerken").first
    knop.wait_for(state="visible", timeout=5000)
    knop.click()
    # De veldenset draagt een `id_prefix` per gezinslid (`p<id>-`), dus het
    # voornaamveld heet `#p<id>-first_name` en niet `#first_name`.
    page.wait_for_selector("input[id$='-first_name']", timeout=5000)


SCREENS: tuple[Screen, ...] = (
    # Public — judged phone-first.
    Screen("public-home", "/", admin=False),
    Screen("public-activiteiten", "/activiteiten", admin=False),
    Screen("public-inschrijfmodal", "/activiteiten", admin=False, viewport_only=True,
           action=_open_register_modal),
    Screen("public-word-lid", "/lid-worden", admin=False),
    Screen("public-formulier", "/formulier/tok-e2e-open", admin=False),
    # Admin — judged desktop-first.
    Screen("admin-dashboard", "/admin", admin=True),
    Screen("admin-betalingen", "/admin/betalingen", admin=True),
    Screen("admin-leden", "/admin/leden", admin=True),
    Screen("admin-activiteit-detail", "/admin/activiteiten", admin=True,
           action=lambda page: _open_first_link(
               page, "E2E-activiteit", "**/admin/activiteiten/*")),
    Screen("admin-formulierbouwer", "/admin/formulieren", admin=True,
           action=lambda page: _open_first_link(
               page, "E2E-formulier", "**/admin/formulieren/*")),
    # The living component kit — review-round material.
    Screen("admin-design-system", "/admin/design-system", admin=True),
    # Ledenflow (#1183) — het beeldmateriaal voor de publieke uitlegpagina over
    # aanmelden, je gegevens nakijken en je lidmaatschap verlengen. Telefoon-eerst,
    # want zo'n pagina wordt vooral op een telefoon gelezen.
    #
    # Uit de SEED en niet met de hand: HDEV draagt echte ledenrecords, dus een
    # afdruk van het gezinsscherm daar zet naam en adres van een echt lid op een
    # publieke pagina — een lek dat geen grep vindt, want het zit in een afbeelding.
    Screen("leden-aanmelden", "/aanmelden", admin=False, sessie=None),
    Screen("leden-aanmelden-code", "/aanmelden", admin=False, sessie=None,
           action=_vraag_de_code),
    Screen("leden-gezin", "/leden/gezin", admin=False, sessie="lid"),
    Screen("leden-gezin-bewerken", "/leden/gezin", admin=False, sessie="lid",
           action=_bewerk_eerste_gezinslid),
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
    Screen("leden-verlengen", "/leden/gezin", admin=False, sessie="lid-verlopen"),
)


def _sessiewaarden() -> dict[str, str]:
    """Eén sessiewaarde per rol die de reeks nodig heeft (#1183).

    De ledenadressen komen uit `seed_e2e` en niet uit een lijstje hier: één bron,
    zodat een hernoemd seed-gezin deze tool meteen laat struikelen in plaats van
    stilletjes een leeg scherm te fotograferen.
    """
    from app.domains.auth.api import make_session_value

    from seed_e2e import MARKER_EMAIL, MARKER_EMAIL_VERLOPEN

    admin = os.environ.get("E2E_ADMIN_EMAIL")
    if not admin:
        from tests.conftest import SEEDED_ADMIN_EMAIL

        admin = SEEDED_ADMIN_EMAIL
    return {
        "admin": make_session_value(admin),
        "lid": make_session_value(MARKER_EMAIL),
        "lid-verlopen": make_session_value(MARKER_EMAIL_VERLOPEN),
    }


def _zet_sessie(page, waarde: Optional[str]) -> None:
    """De cookie voor dit scherm — eerst wissen, dan zetten (#1183).

    Wissen hoort erbij: zonder dat draagt `/aanmelden` nog de sessie van het
    vorige scherm en fotografeer je een aangemelde bezoeker op het aanmeldscherm.
    """
    page.context.clear_cookies()
    if waarde:
        login_met_sessie(page, waarde)


def _capture(page, screen: Screen, width: dict, out_dir: Path) -> Path:
    page.set_viewport_size(width)
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
        "() => !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')")
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
        print(f"refused: E2E_BASE_URL points at {host!r} — this tool captures "
              "seeded LOCAL screens only, never a live environment.",
              file=sys.stderr)
        return 2

    out_dir = Path(argv[1]) if len(argv) > 1 else Path("screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    sessies = _sessiewaarden()
    captured: list[Path] = []
    missing: list[str] = []

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        context = browser.new_context(base_url=BASE, reduced_motion="reduce")
        page = context.new_page()

        for screen in SCREENS:
            if screen.sessie is not None and screen.sessie not in sessies:
                missing.append(f"{screen.key}: onbekende sessie {screen.sessie!r}")
                continue
            # Primary width first: phone for public, desktop for admin.
            widths = (DESKTOP, PHONE) if screen.admin else (PHONE, DESKTOP)
            for width in widths:
                try:
                    _zet_sessie(page, sessies.get(screen.sessie) if screen.sessie else None)
                    captured.append(_capture(page, screen, width, out_dir))
                except Exception as exc:  # noqa: BLE001 - report, don't die mid-set
                    missing.append(f"{screen.key} @ {width['width']}: {exc}")
        browser.close()

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
