"""#677 — een select en een input zijn even hoog.

#659 trok de klassen gelijk (alles via `ui.label` en de control-macro's) en dat
was nodig, maar het hoogteverschil bleef. De oorzaak ligt een laag dieper: beide
controls dragen dezelfde padding, lettergrootte en regelhoogte, maar er stond geen
expliciete HOOGTE. Zonder die bepaalt de browser zelf hoe hoog een `<select>`
wordt — die krijgt intrinsieke ruimte voor zijn pijltje en een eigen
minimumhoogte, een `<input>` niet.

Enkele pixels verschil, en omdat de compacte vormen `items-end` gebruiken zakt het
LABEL boven de kortere kolom mee. Zelfde zichtbare fout als #656, andere oorzaak.

Een rendertest op klassen is hier zwak: de HTML klopte al. Dit meet wat de browser
ervan maakt. Eén meting op de "+ Product"-vorm dekt de hele kit, want de
maatvoering komt uit één gedeelde bron.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (BASE, Activiteitdetail, controlhoogtes,  # noqa: E402
                                login_als_admin)


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
        login_als_admin(page, email, make_session_value(email))
        page.goto("/admin/activiteiten")
        if page.locator("main").count() == 0:
            browser.close()
            pytest.skip("adminsessie niet aanvaard door deze omgeving")
        yield page
        browser.close()


def test_input_en_select_zijn_even_hoog(admin_page):
    """De "+ Product"-vorm: vier tekstvelden en één keuzelijst naast elkaar."""
    scherm = Activiteitdetail(admin_page)
    if not scherm.open_eerste():
        _ontbreekt("geen activiteit om te openen")

    # De toevoegvorm staat dicht; ze openen zet de velden in beeld.
    knop = admin_page.get_by_role("button", name="+ Product").first
    if knop.count() == 0:
        _ontbreekt("dit onderdeel heeft geen '+ Product'-vorm")
    knop.click()
    admin_page.wait_for_timeout(200)

    hoogtes = controlhoogtes(admin_page, 'form[hx-post*="/producten"]')
    if len(hoogtes) < 2:
        _ontbreekt("de toevoegvorm toont geen velden om te meten")

    uniek = set(hoogtes.values())
    assert len(uniek) == 1, (
        "de velden in één vorm zijn niet even hoog — een select krijgt van de "
        f"browser een eigen minimumhoogte als die niet vastligt: {hoogtes}")


def test_datum_en_tijdvelden_lopen_mee(admin_page):
    """`date` en `time` dragen in elke browser hun eigen intrinsieke maat, en ze
    staan op dit scherm direct naast gewone tekstvelden."""
    scherm = Activiteitdetail(admin_page)
    if not scherm.open_eerste():
        _ontbreekt("geen activiteit om te openen")
    if scherm.datumregel().count() == 0:
        _ontbreekt("de activiteit heeft geen datumregel")

    scherm.bewerk_de_eerste_datum()
    admin_page.wait_for_timeout(200)

    hoogtes = controlhoogtes(admin_page, 'form[hx-post*="/datums/"]')
    if len(hoogtes) < 2:
        _ontbreekt("de datumvorm toont geen velden om te meten")
    assert len(set(hoogtes.values())) == 1, (
        f"datum- en tijdvelden lopen niet gelijk met de rest: {hoogtes}")
