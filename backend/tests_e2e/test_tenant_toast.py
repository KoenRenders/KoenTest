"""E2E: de bevestiging op het tenantscherm is écht zichtbaar (#748).

Dit is de derde keer vandaag dat een groene servertest iets anders bewees dan wat we
wilden weten (#718, #726, #736). De servertest van #742 controleerde of het antwoord
de toast bevátte — en dat deed het. Het ging mis bij het samenvoegen.

**Waarom juist dit scherm.** De drie andere schermen krijgen hun toast in een
FRAGMENT, dat in een klein doel geswapt wordt; de `#toasts`-host staat daarbuiten en
overleeft. Dit scherm doet `hx-target="body" hx-swap="innerHTML"` en krijgt een
volledige pagina terug. htmx haalt dan het out-of-band element uit het antwoord, zet
de toast in de bestaande host, en vervangt daarna het hele lichaam — inclusief die
host — door de verse, lege versie uit datzelfde antwoord.

Gemeten vóór de fix, op `/admin/tenants/2`:

    [t+200ms]  hosts=1 kinderen=0
    [t+1500ms] hosts=1 kinderen=0

en erna 1 kind, zichtbaar. Het antwoord bevatte in beide gevallen een toast.

De scheidslijn is dus niet "toast ja/nee" maar de VORM van het antwoord — dezelfde
grens die #718 trok, toen voor de navigatie.

De laatste test is er omdat #718 langs precies deze weg kan terugkomen: dit is een
body-swap, en de navigatie hoort te blijven staan.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `toast_host()`
zonder de vlag aangeroepen in admin_base.html en het oob-blok terug in
admin_tenant.html — de eerste test valt om met nul kinderen in de host.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie  # noqa: E402


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


def _open_editor(page):
    """De editor van één tenant. Bewust niet de eerste link op het scherm: dat is
    "Nieuwe tenant", en daar staat een ander formulier."""
    page.goto("/admin/tenants")
    page.wait_for_timeout(400)
    link = page.locator(
        "xpath=//a[starts-with(@href,'/admin/tenants/') and "
        "translate(substring-after(@href,'/admin/tenants/'),'0123456789','')='']").first
    if link.count() == 0:
        _ontbreekt("geen tenant om te bewerken op deze omgeving")
    link.click()
    page.wait_for_selector("form[hx-post^='/admin/tenants/']", timeout=5000)


def test_de_bevestiging_is_zichtbaar_na_het_opslaan(admin_page):
    _open_editor(admin_page)
    assert admin_page.locator("#toasts > *").count() == 0, (
        "er stond al een bevestiging vóór het opslaan")

    admin_page.get_by_role("button", name="Opslaan").first.click()
    admin_page.wait_for_timeout(800)

    toast = admin_page.locator("#toasts > *")
    assert toast.count() == 1, (
        "de bevestiging is geplaatst en meteen weggegooid — de host wordt bij een "
        "body-swap zelf mee vervangen (#748)")
    assert toast.first.is_visible()
    assert "Opgeslagen" in toast.first.inner_text()


def test_de_navigatie_staat_er_nog_na_het_opslaan(admin_page):
    """#718 kan langs deze weg terugkomen: dit is een body-swap."""
    _open_editor(admin_page)
    admin_page.get_by_role("button", name="Opslaan").first.click()
    admin_page.wait_for_timeout(800)

    assert admin_page.locator("#admin-nav-zijbalk").count() == 1, (
        "de zijbalk is uit het lichaam verdwenen")
