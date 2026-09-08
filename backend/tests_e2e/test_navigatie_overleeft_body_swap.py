"""E2E: de menubalk overleeft een formulier dat `body` vervangt (#718).

Gemeld op HDEV: vernieuw je op `/leden/gezin` je lidmaatschap via overschrijving,
dan staan de betaalinstructies er wel maar is de navigatie weg. Logo en baseline
blijven staan.

**Alleen een echte browser kan dit aantonen.** De server antwoordt met een correcte
200 en de navigatie zit ín die HTML — een servertest ziet dus niets. Het gaat mis
bij het samenvoegen: sinds #714 dragen de navigatiecontainers `hx-swap-oob`, htmx
licht die uit het antwoord vóór de gewone swap, en dit formulier vervangt met
`hx-target="body" hx-swap="innerHTML"` het hele lichaam door wat overblijft.

**Waarom deze test een gezinslid toevoegt en niet vernieuwt.** Het vernieuwformulier
verschijnt enkel binnen het hernieuwvenster (`MEMBERSHIP_RENEWAL_START_MD`), dus een
test die dáárop mikt zou de helft van het jaar overslaan — en een overgeslagen test
is tussen groene runs onzichtbaar (#644). Het toevoegformulier staat op dezelfde
pagina, in dezelfde schil, met hetzelfde `hx-target="body" hx-swap="innerHTML"`, en
krijgt hetzelfde volledige antwoord terug. Het is dus dezelfde samenvoeging.

De tegenhanger staat in `test_actieve_navigatie.py`: die bewaakt dat een gebooste
navigatie de actieve markering nog steeds verplaatst (#714). Samen leggen ze de
grens vast — out-of-band bij een boost, gewoon meegeleverd bij al de rest. Slaagt
deze test terwijl die andere zakt, dan is #714 teruggedraaid in plaats van
gerepareerd.

Kapotgemaakt om te controleren dat deze test rood kan worden: `nav_oob` hard op
True gezet (het gedrag van vóór #718) → de menubalk is na het toevoegen weg en de
assert valt om.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (BASE, Gezinsportaal,  # noqa: E402
                                login_met_sessie)


def _ontbreekt(reden: str) -> None:
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e-seed geladen maar: {reden}")
    pytest.skip(reden)


@pytest.fixture(scope="module")
def lid_page():
    try:
        from app.domains.auth.api import make_session_value
        from seed_e2e import MARKER_EMAIL

        email = os.environ.get("E2E_LID_EMAIL") or MARKER_EMAIL
    except Exception as exc:  # pragma: no cover - alleen in een kale omgeving
        pytest.skip(f"backend niet importeerbaar voor de sessiewaarde: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        login_met_sessie(page, make_session_value(email))
        yield page
        browser.close()


def test_de_menubalk_staat_er_nog_na_een_body_swap(lid_page):
    portaal = Gezinsportaal(lid_page).open()
    if lid_page.get_by_role("button", name="+ Gezinslid toevoegen").count() == 0:
        _ontbreekt("geen gezinsportaal voor dit lid op deze omgeving")

    balk = portaal.navigatiebalk()
    assert balk.is_visible(), "de menubalk stond er vóór de actie al niet"
    voor = balk.inner_text()

    portaal.voeg_gezinslid_toe("E2E", "Navigatie")

    assert balk.count() == 1, (
        "de menubalk is uit het lichaam verdwenen — htmx heeft haar out-of-band uit "
        "het antwoord gelicht en de rest over het lichaam gelegd (#718)")
    assert balk.is_visible()
    assert balk.inner_text() == voor, "de menubalk is wél gebleven maar veranderd"
