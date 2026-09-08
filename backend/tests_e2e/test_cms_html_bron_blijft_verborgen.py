"""E2E: na Opslaan verschijnt de HTML-bron niet als een tweede leeg vak (#726).

Alleen een echte browser kan dit aantonen. Het serverantwoord is correct — de
textarea draagt `x-show="src"` en `x-cloak`, de `x-data`-div eromheen staat er, en
`admin_base.html` draagt de `[x-cloak]`-regel. Het ging mis ná de swap.

**Wat er gemeten is**, met de tijden erbij, want die zijn het bewijs: op t+50 ms na
de klik stond er `display: none` en was `x-cloak` weg — Alpine had dus gewerkt — en
tussen t+50 en t+150 ms verdween het style-attribuut en werd het vak zichtbaar.

Dat laatste is htmx: `style` staat in `attributesToSettle`, dus een element met een
`id` krijgt na de settle-vertraging de attributen van het serverantwoord terug. Daar
stond geen style, dus htmx wiste precies het `display: none` dat Alpine er net op had
gezet. De fix zet die style server-side mee; `src` begint altijd op false, dus
verborgen is de juiste beginstand.

**Niet Trix.** Dat was de eerste verdenking (de editor maakt bij het verbinden zijn
eigen `<trix-toolbar>` en voegt die in de x-data-scope in). Met de `<trix-editor>`
volledig uit de template bleef het vak na het opslaan even goed staan, dus die
verklaring is gemeten en verworpen.

De tweede test is de tegenproef: zonder haar staat de eerste ook groen wanneer de
toggle gesloopt is in plaats van gerepareerd, en dan is de HTML-bron onbereikbaar.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, Paginascherm, login_met_sessie  # noqa: E402


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


def test_de_html_bron_blijft_verborgen_na_opslaan(admin_page):
    scherm = Paginascherm(admin_page).open_eerste()
    if scherm is None:
        _ontbreekt("geen cms-pagina op deze omgeving")

    assert not scherm.htmlbron().is_visible(), "het vak stond vóór het opslaan al open"
    inhoud_voor = scherm.editorinhoud()

    scherm.opslaan()

    assert not scherm.htmlbron().is_visible(), (
        "de HTML-bron staat als tweede, leeg invoervak onder de editor")
    assert scherm.editorinhoud() == inhoud_voor, (
        "de inhoud van de editor is bij het opslaan veranderd")


def test_de_html_bron_gaat_daarna_nog_steeds_open(admin_page):
    """De tegenproef: verborgen houden mag de knop niet kapotmaken."""
    scherm = Paginascherm(admin_page).open_eerste()
    if scherm is None:
        _ontbreekt("geen cms-pagina op deze omgeving")

    scherm.opslaan()
    scherm.toon_html_bron()

    assert scherm.htmlbron().is_visible(), (
        "de HTML-bron is na het opslaan niet meer te openen")
