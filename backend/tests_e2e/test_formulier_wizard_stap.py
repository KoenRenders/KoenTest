"""E2E: de wizard controleert de verplichte velden van de huidige stap (#724).

Je kon door een formulier met secties heen klikken zonder de verplichte vragen te
beantwoorden. De server weigerde wél — en correct, mét het overslaan van de niet
doorlopen secties — maar dat hoorde je pas bij Verzenden, en de foutweg zette je
terug op stap 0.

**Dit hoort in een browser.** Het `required`-attribuut staat er bewust niet op
(#688): de browser valideert bij verzending het hele formulier, ook stappen die je
door een sprong nooit ziet, en kan een verborgen veld niet aanwijzen. De controle
per stap is dus JavaScript, en of ze werkt is browsergedrag.

De derde test is de belangrijkste en het makkelijkst te vergeten: een verplicht veld
in een **overgeslagen** sectie mag niets blokkeren. Zonder haar is de nieuwe
controle strenger dan de server, en dan kan je een vertakt formulier niet meer
verzenden — een storing die erger is dan de bug.

De serverkant (de 422 blijft, en de wizard opent op de stap van het gemelde veld)
staat in `tests/test_formulier_wizard_startstap.py`.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `if
(!this.controleer()) return;` uit `next()` gehaald → de eerste test valt om (de
wizard springt gewoon door) en de andere twee blijven groen.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE  # noqa: E402


@pytest.fixture(scope="module")
def vertakt_formulier():
    """Drie secties met een sprong: A gaat naar 2, B slaat 2 over en gaat naar 3.

    Elke sectie heeft een verplicht veld, zodat "blokkeert het?" en "blokkeert het
    te veel?" allebei toetsbaar zijn op hetzelfde formulier.
    """
    import secrets

    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.forms.models import (Form, FormField, FormFieldOption,
                                          FormSection)

    db = SessionLocal()
    token = "e2e724-" + secrets.token_urlsafe(6)
    form = Form(title="E2E Vertakt", status="open", is_anonymous=True,
                share_token=token)
    db.add(form)
    db.flush()
    secties = []
    for i, titel in enumerate(("Route", "Alleen bij A", "Slot")):
        sec = FormSection(form_id=form.id, title=titel, position=i)
        db.add(sec)
        secties.append(sec)
    db.flush()

    keuze = FormField(form_id=form.id, section_id=secties[0].id, field_type="radio",
                      label="Welke route?", position=0, required=True)
    db.add(keuze)
    db.flush()
    db.add(FormFieldOption(field_id=keuze.id, label="A", position=0))
    db.add(FormFieldOption(field_id=keuze.id, label="B", position=1,
                           skip_to_section_id=secties[2].id))
    for sec, label in ((secties[1], "Waarom A?"), (secties[2], "Slotvraag")):
        db.add(FormField(form_id=form.id, section_id=sec.id, field_type="text",
                         label=label, position=0, required=True))
    db.commit()
    db.close()
    return token


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE)
        yield p
        browser.close()


def _stap(page, nr: int):
    return page.locator(f'[data-step="{nr}"]')


def test_een_leeg_verplicht_veld_houdt_de_stap_vast(page, vertakt_formulier):
    """Het gemelde geval: Volgende doet niets zonder antwoord — maar wel zichtbaar."""
    page.goto(f"/formulier/{vertakt_formulier}")
    page.wait_for_selector('[data-step="0"]', timeout=5000)

    page.get_by_role("button", name="Volgende").click()
    page.wait_for_timeout(300)

    assert _stap(page, 0).is_visible(), "de wizard sprong door met een leeg veld"
    assert not _stap(page, 1).is_visible()
    gemarkeerd = page.locator('[data-step="0"] [aria-invalid="true"]')
    assert gemarkeerd.count() > 0, (
        "de onbeantwoorde vraag is niet gemarkeerd — dan lijkt de knop kapot")


def test_ingevuld_gaat_de_stap_wel_door(page, vertakt_formulier):
    """De tegenhanger: zonder haar zou "blokkeer altijd" ook groen staan."""
    page.goto(f"/formulier/{vertakt_formulier}")
    page.wait_for_selector('[data-step="0"]', timeout=5000)

    page.get_by_label("A", exact=True).check()
    page.get_by_role("button", name="Volgende").click()
    page.wait_for_timeout(300)

    assert _stap(page, 1).is_visible(), "de wizard blijft steken op een ingevulde stap"


def test_een_verplicht_veld_in_een_overgeslagen_sectie_blokkeert_niets(
        page, vertakt_formulier):
    """De controle mag niet strenger zijn dan de server.

    Route B slaat sectie 2 over. Het verplichte veld daarin blijft dus leeg, en dat
    hoort het verzenden niet tegen te houden — de server slaat die sectie ook over.
    """
    page.goto(f"/formulier/{vertakt_formulier}")
    page.wait_for_selector('[data-step="0"]', timeout=5000)

    page.get_by_label("B", exact=True).check()
    page.get_by_role("button", name="Volgende").click()
    page.wait_for_timeout(300)
    assert _stap(page, 2).is_visible(), "de sprong naar de laatste sectie werkte niet"

    page.locator('[data-step="2"] input[type=text]').first.fill("Klaar")
    page.get_by_role("button", name="Verzenden").click()
    page.wait_for_timeout(800)

    assert "verzonden" in page.content().lower() or "bedankt" in page.content().lower(), (
        "het formulier is niet verzonden terwijl alle bereikte velden ingevuld waren")
