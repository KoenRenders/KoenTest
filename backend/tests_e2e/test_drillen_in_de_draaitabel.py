"""Klikt een jaartal in de draaitabel écht door? (#899 stap 2)

Deze test bestaat om een reden die pijnlijk herkenbaar is: het onderdeel stond er
en de verbinding niet. De drill-knop werd gerenderd met de juiste naam en de juiste
waarde, en de eenheidstests keken naar de markup en naar de route — allebei groen.
Maar de knop droeg geen `hx-get`, en `type="button"` verstuurt niets. Klikken deed
letterlijk niets.

De oorzaak zat in de reden die in het commentaar van de macro stond: de kit kent
dit domein niet en kreeg dus een naam om terug te sturen — maar ze kende evenmin de
URL waar dat heen moest, en die was nergens meegegeven.

**Alleen een echte browser bewijst dat een knop iets doet.** Een eenheidstest die
vaststelt dat het element doorklikbaar gerenderd is, herhaalt precies de blinde
vlek: ze leest dezelfde markup waarin het ontbrak.

Zelfde vorm als #613 punt 3 en als de `sort_order` die uit het formulier verdween
terwijl de route hem nog aannam.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin  # noqa: E402


def _wacht_op(page, objectsleutel: str) -> None:
    """Wacht tot de staat het object draagt, en zeg wat er misging als niet.

    Op de TOESTAND en niet op de klok: een vaste pauze gaat groen of rood met de
    belasting van de machine. `state="attached"` en niet de standaard "visible":
    de staat zit in verborgen invoer en die wordt nooit zichtbaar.
    """
    from playwright.sync_api import TimeoutError as PWTimeout

    try:
        page.wait_for_selector(f'input[name="object"][value="{objectsleutel}"]',
                               state="attached", timeout=15000)
    except PWTimeout:
        paneel = [u for u in getattr(page, "verzoeken", []) if "paneel" in u]
        raise AssertionError(
            f"de staat kwam niet op {objectsleutel}. Verzoeken naar het paneel: "
            f"{paneel[-3:] or 'GEEN — de klik vertrok niet'}") from None


def _ontbreekt(reden: str) -> None:
    """Ontbrekende data: skip tegen een echte omgeving, fout onder de e2e-seed.

    Zelfde afweging als in `test_beheer_flows.py`: tegen HDEV zegt "geen
    betalingen" iets over die omgeving, tegen de seed betekent het dat het scherm
    ze niet toont — een bevinding. Een skip is tussen groene runs onzichtbaar, en
    dat is precies hoe een test maandenlang niets kan bewijzen (#644).
    """
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e-seed geladen maar: {reden}")
    pytest.skip(reden)

# Een draaitabel op jaar met één maat en geen kolomas: de kortste weg naar een
# scherm waarin een jaartal doorklikbaar hoort te zijn.
#
# `/nieuw` en NIET `/paneel`: dat tweede adres levert het fragment, zonder schil en
# dus zonder htmx. In een pagina zonder htmx doet élke knop niets, dus een test
# daarop zou altijd falen — en zou over de verkeerde oorzaak vallen. Dat is precies
# de eerste ronde van deze test geweest.
# Op een ROLDATUM en niet op de gedeelde datum, en dat is geen willekeur. Een rol
# is een ALIAS op `d_date` (#895), en juist die naam bestaat niet in de databank —
# dus juist daar breekt een plek die vergeet te vertalen. De eerste versie van deze
# test drilde op `date_year`, waar alias en sleutel samenvallen, en stond groen
# terwijl klikken op een betaaldatum een foutbanner gaf.
#
# En op de STARTDATUM van een activiteit en niet op de betaaldatum, omdat de
# e2e-seed geen betaalde betaling heeft: elke betaaldatum is dan leeg, de enige rij
# heet "Onbekend", en daar hoort juist niet op gedrild te worden. De activiteiten
# hebben wél datums, dus dit is de rol die in een verse databank iets te klikken
# geeft.
PANEEL = ("/admin/rapporten/nieuw?object=start_date_year&object=activity_count"
          "&layout=pivot&pivot_column=&no_column=1")


def _admin_email() -> str:
    override = os.environ.get("E2E_ADMIN_EMAIL")
    if override:
        return override
    from tests.conftest import SEEDED_ADMIN_EMAIL

    return SEEDED_ADMIN_EMAIL


@pytest.fixture(scope="module")
def admin_page():
    try:
        from app.domains.auth.api import make_session_value

        email = _admin_email()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"backend niet importeerbaar voor de sessiewaarde: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        login_als_admin(page, email, make_session_value(email))
        # Wat htmx werkelijk verstuurt. Zonder dit staat er bij een falende klik
        # alleen "de toestand veranderde niet", en dan weet je niet of het verzoek
        # niet vertrok of of de server iets anders terugstuurde.
        page.verzoeken = []
        page.on("request", lambda r: page.verzoeken.append(r.url))
        page.goto("/admin/rapporten")
        if page.locator("text=Rapporten").count() == 0:
            browser.close()
            pytest.skip("adminsessie niet aanvaard door deze omgeving")
        yield page
        browser.close()


def test_klikken_op_een_jaartal_drilt_naar_kwartaal(admin_page):
    """De klik, in een echte browser — niet de markup en niet de route."""
    admin_page.goto(PANEEL)
    knop = admin_page.locator('button[name="drill"]').first
    if knop.count() == 0:
        _ontbreekt("geen activiteit met een datum, dus geen jaartal om te drillen")

    jaar = knop.inner_text().strip()
    knop.click()

    # Wachten op de TOESTAND en niet op de klok: een vaste pauze gaat groen of
    # rood met de belasting van de machine, en dat is precies het soort test dat
    # later voor een echte bevinding wordt aangezien. Slaat er niets aan, dan
    # verloopt dit met een melding die zegt wat er ontbrak.
    #
    # `state="attached"` en niet de standaard "visible": de staat zit in VERBORGEN
    # invoer, en die wordt nooit zichtbaar.
    _wacht_op(admin_page, "start_date_quarter")

    inhoud = admin_page.content()
    assert f'value="{jaar}"' in inhoud, (
        "de filter op het aangeklikte jaar hoort zichtbaar in de staat te staan")


def test_terug_omhoog_brengt_je_terug(admin_page):
    """De weg terug, ook door de browser: één knop, één niveau omhoog."""
    admin_page.goto(PANEEL)
    knop = admin_page.locator('button[name="drill"]').first
    if knop.count() == 0:
        _ontbreekt("geen activiteit met een datum")
    knop.click()
    _wacht_op(admin_page, "start_date_quarter")

    terug = admin_page.locator('button[name="rollup"]').first
    assert terug.count() > 0, "na het drillen hoort er een weg terug te staan"
    terug.click()
    _wacht_op(admin_page, "start_date_year")

    inhoud = admin_page.content()
    assert 'name="filter" value="start_date_year"' not in inhoud, (
        "oprollen hoort de filter mee terug te nemen; blijft hij staan, dan is "
        "het rapport stilletjes nog op dat jaar")
