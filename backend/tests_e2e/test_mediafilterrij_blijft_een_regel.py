"""#1138 punt 1 — de filterrij op /admin/media blijft op één regel.

Koen zag zoekveld en de drie soort-knoppen op regel één en *Alle activiteiten*
eronder, op een venster van 1440 px. De oorzaak zit niet in de structuur (de
keuzelijst staat al in dezelfde flex-rij, #1079 is niet geschonden) maar in een
maat: een `<select>` is zo breed als haar LANGSTE optie, dus de langste
activiteitentitel bepaalde of de rij brak.

Waarom dit een e2e-test is en geen rendertest: de opmaak was al goed. Alleen de
browser weet hoe breed de keuzelijst van haar opties wordt en waar flex-wrap
dan toeslaat.

Gemeten op 21 september 2026, beheerscherm 1024 px breed bij een venster van
1440 px:

  - met "E2E-activiteit (2026)" was de rij 339 + 431 + 230 + 24 = 1024 van
    1024 px — exact vol. Geen marge, dus elke echte titel breekt haar.
  - met Koens eigen "Gezinsuitstap Irrland (2026)" paste ze nog nét.
  - met de titel die `seed_e2e.py` nu zet werd de keuzelijst 399 px en wrapte
    de rij op ELKE gemeten breedte, 1600 px incluis.
  - na de reparatie (keuzelijst `max-w-[14rem]`): één regel tot en met een
    venster van 1280 px, breken vanaf 1152 px.

De ondergrens van het zoekveld bleef `min-w-[14rem]`. Ze verlagen naar 12rem
hield de rij ook op 1152 px heel, maar die klasse is de gedeelde referentie van
alle elf filterbalken en `tests/test_filterbalk_op_een_regel.py` bewaakt haar
(#1079/#996) — dat is precies de poort die voorkomt dat één scherm wegdrijft.
Die poort ving deze wijziging dan ook.

Tegenproef (uitgevoerd, beide richtingen): `max-w-[14rem]` uit
`admin_media.html` halen en de css herbouwen maakt alle DRIE de tests rood.
De eerste twee met "de filterrij breekt bij 1440 px: hoogte 88 px, hoogste
kind 38 px"; de derde omdat de ongebonden keuzelijst dan 399 px meet in een
rij van 358 px en er dus buiten steekt. Dat laatste had ik niet verwacht en
het is een tweede reden voor de bovengrens: zonder haar loopt het scherm op
mobiel horizontaal over.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin, pagina_klaar  # noqa: E402

# Eén JS-meting voor de drie tests. `wrapt` vergelijkt de hoogte van de rij met
# die van haar hoogste kind: staat alles op één regel, dan zijn die gelijk. De
# marge van 4 px vangt de uitlijning op — de knoppen staan een paar pixel lager
# dan het zoekveld zonder daarom op een tweede regel te staan.
_METEN = """() => {
  const rij = document.querySelector('form [class*="flex-wrap"]');
  if (!rij) return null;
  const r = rij.getBoundingClientRect();
  const kinderen = [...rij.children].map(x => {
    const b = x.getBoundingClientRect();
    return {breedte: Math.round(b.width), hoogte: Math.round(b.height)};
  });
  const hoogste = Math.max(...kinderen.map(k => k.hoogte));
  return {breedte: Math.round(r.width), hoogte: Math.round(r.height),
          hoogste, kinderen,
          heeftKeuzelijst: rij.querySelector('select') !== null};
}"""


def _ontbreekt(reden: str) -> None:
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e-seed geladen maar: {reden}")
    pytest.skip(reden)


@pytest.fixture(scope="module")
def mediascherm():
    try:
        from app.domains.auth.api import make_session_value
        from tests.conftest import SEEDED_ADMIN_EMAIL

        email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    except Exception as exc:  # pragma: no cover - alleen in een kale omgeving
        pytest.skip(f"backend niet importeerbaar voor de sessiewaarde: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
        login_als_admin(page, email, make_session_value(email))
        # Soort `activity_photo`: alleen daar toont het scherm de keuzelijst, en
        # die is precies het onderdeel dat de rij brak.
        page.goto("/admin/media?kind=activity_photo")
        if page.locator("main").count() == 0:
            browser.close()
            pytest.skip("adminsessie niet aanvaard door deze omgeving")
        pagina_klaar(page)
        yield page
        browser.close()


def _maten(page, breedte: int) -> dict:
    # Geen vaste wachttijd (#997-poort): `set_viewport_size` herberekent de
    # opmaak synchroon, en `evaluate` is een aparte ronde naar de browser — de
    # meting ziet dus al de nieuwe breedte.
    page.set_viewport_size({"width": breedte, "height": 900})
    maten = page.evaluate(_METEN)
    if maten is None:
        _ontbreekt("geen filterrij gevonden op /admin/media")
    if not maten["heeftKeuzelijst"]:
        # Zonder activiteitenfoto's rendert het scherm de keuzelijst niet, en
        # dan meet deze test de rij zonder het onderdeel dat haar brak.
        _ontbreekt("geen activiteit met media, dus geen keuzelijst in de rij")
    return maten


@pytest.mark.parametrize("breedte", [1440, 1280])
def test_de_filterrij_blijft_een_regel(mediascherm, breedte):
    """1440 px is Koens scherm; 1280 px is de smalste gewone laptopbreedte."""
    m = _maten(mediascherm, breedte)
    assert m["hoogte"] <= m["hoogste"] + 4, (
        f"de filterrij breekt bij {breedte} px: hoogte {m['hoogte']} px, "
        f"hoogste kind {m['hoogste']} px — kinderen {m['kinderen']}")


def test_op_mobiel_breekt_ze_maar_loopt_ze_niet_over(mediascherm):
    """Breken mag (80% van het bezoek is mobiel), buiten de rij steken niet.

    Deze test bewaakt de andere kant van de reparatie: een bovengrens die de
    keuzelijst afkapt mag haar niet breder laten worden dan het scherm.
    """
    m = _maten(mediascherm, 390)
    te_breed = [k for k in m["kinderen"] if k["breedte"] > m["breedte"]]
    assert not te_breed, (
        f"op 390 px steekt er iets buiten de filterrij ({m['breedte']} px): "
        f"{te_breed}")
