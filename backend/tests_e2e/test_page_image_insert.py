"""E2E #1173: de knop voegt een afbeelding in, en ze staat op de pagina.

**Waarom dit in een echte browser moet.** `tests/test_page_image_1173.py` toetst de
serverhelft op HTML die ik uit een headless Chromium gemeten heb — maar zo'n
vastgelegde constante veroudert stil. Verandert Trix zijn serialisatie, dan blijft
die test groen op HTML die niemand meer produceert, en zou de pagina intussen een
afbeelding zonder alt tonen (of helemaal geen).

Deze test sluit die kier: ze klikt de échte knop in de échte editor en kijkt wat er
in de verborgen invoer belandt. Twee beweringen, en de eerste is de belangrijkste:

1. De editor bewaart de afbeelding als bijlage **met de alt in de JSON**. Dat is
   precies de aanname waar de serverhelft op rust. Klopt ze niet meer, dan faalt
   hier de assert met de werkelijke HTML in de melding.
2. Na opslaan staat op de gerenderde pagina een `<img>` met die alt — de weg langs
   `image_alt_from_attachment()` en de sanitisatie, van klik tot publicatie.

**Waarom niet via `insertHTML('<img alt=…>')`, wat het issue voorstelde:** Trix'
parser maakt van elke `<img>` een bijlage en houdt daarbij alleen src, width en
height over. Gemeten in dezelfde opstelling als deze test; de alt was weg vóór er
iets bewaard werd.

Kapotgemaakt om te controleren dat ze rood kan worden (gemeten): `alt: alt.trim()`
uit de `Trix.Attachment` in `admin_pagina.html` gehaald → de eerste assert valt om
("de alt staat niet in de bijlage-JSON"), en de tweede erna.
"""
import json
import os
import re
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, Paginascherm, login_met_sessie  # noqa: E402

TITEL = "E2E-schermafdruk aanmelden"     # de seed-titel; wordt de voorgestelde alt


def _ontbreekt(reden: str) -> None:
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e-seed geladen maar: {reden}")
    pytest.skip(reden)


@pytest.fixture(scope="module")
def admin_page():
    try:
        from app.domains.auth.api import make_session_value
        from tests.conftest import SEEDED_ADMIN_EMAIL

        email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    except Exception as exc:  # pragma: no cover - alleen in een kale omgeving
        pytest.skip(f"backend niet importeerbaar voor de sessiewaarde: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        login_met_sessie(page, make_session_value(email))
        yield page
        browser.close()


def test_de_knop_voegt_een_afbeelding_met_alt_in(admin_page):
    scherm = Paginascherm(admin_page).open_eerste()
    if scherm is None:
        _ontbreekt("geen cms-pagina op deze omgeving")

    admin_page.get_by_role("button", name="Afbeelding").first.click()
    dialoog = admin_page.get_by_role("dialog")
    expect(dialoog, "het dialoogje ging niet open").to_be_visible()

    keuze = dialoog.locator("button[data-url]").first
    if keuze.count() == 0:
        _ontbreekt("geen pagina-afbeelding in de bibliotheek")

    # De afbeelding moet ook écht laden: een kapotte miniatuur zou hier een
    # keuzeknop met een leeg vak zijn, en dan kiest niemand iets.
    miniatuur = keuze.locator("img")
    assert admin_page.evaluate("el => el.naturalWidth", miniatuur.element_handle()) > 0, (
        "de miniatuur in de kiezer laadt niet")

    keuze.click()
    altveld = dialoog.locator("#cp-alt")
    assert altveld.input_value() == TITEL, (
        f"de alt is niet voorgevuld met de titel uit de bibliotheek: "
        f"{altveld.input_value()!r}")

    altveld.fill("Het aanmeldformulier met de knop Lid worden")
    dialoog.get_by_role("button", name="Invoegen").click()

    # ── 1. Wat de editor ervan maakt ─────────────────────────────────────────
    inhoud = scherm.editorinhoud()
    match = re.search(r'data-trix-attachment="([^"]*)"', inhoud)
    assert match, (
        "de editor heeft geen bijlage bewaard — Trix serialiseert een afbeelding "
        f"blijkbaar anders dan gemeten:\n{inhoud}")
    bijlage = json.loads(match.group(1).replace("&quot;", '"'))
    assert bijlage.get("alt") == "Het aanmeldformulier met de knop Lid worden", (
        "de alt staat niet in de bijlage-JSON, dus de server kan hem niet op de "
        f"<img> zetten: {bijlage}")
    assert "/api/v1/media/" in (bijlage.get("url") or ""), bijlage

    # ── 2. En wat de bezoeker uiteindelijk ziet ──────────────────────────────
    scherm.opslaan()
    paginaid = re.search(r"/admin/paginas/(\d+)", admin_page.url)
    assert paginaid, admin_page.url
    admin_page.goto(f"/admin/paginas/{paginaid.group(1)}/voorbeeld")
    beeld = admin_page.locator("img[alt='Het aanmeldformulier met de knop Lid worden']")
    expect(beeld, "de afbeelding staat niet op de gerenderde pagina, of zonder "
                  "alt — de sanitisatie is de plek waar dat gebeurt").to_have_count(1)
    assert admin_page.evaluate("el => el.naturalWidth", beeld.element_handle()) > 0, (
        "de afbeelding staat er wel maar laadt niet")


def test_slepen_van_een_bestand_blijft_geweigerd(admin_page):
    """De bestandsblokkade in de editor blijft staan (#1173): invoegen gebeurt uit
    de bibliotheek, niet door te slepen — een sleeppad zou een onbeperkte upload
    naar een publieke pagina zijn.

    Getoetst op het gedrag en niet op de aanwezigheid van de listener: het
    `trix-file-accept`-event wordt hier echt afgevuurd, en `defaultPrevented`
    zegt dan of de schil het tegenhoudt.
    """
    scherm = Paginascherm(admin_page).open_eerste()
    if scherm is None:
        _ontbreekt("geen cms-pagina op deze omgeving")

    geweigerd = admin_page.evaluate("""() => {
        const e = new CustomEvent("trix-file-accept", { cancelable: true, bubbles: true });
        document.getElementById("cp-trix").dispatchEvent(e);
        return e.defaultPrevented;
    }""")

    assert geweigerd, (
        "de editor accepteert weer bestanden — dat is een onbeperkt uploadpad "
        "naar een publieke pagina")
