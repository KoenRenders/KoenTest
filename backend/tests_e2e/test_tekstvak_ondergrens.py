"""E2E: een leeg tekstvak opent op het aantal regels dat het vroeg (#1037).

Regressie van #1027. Een inline `style.height` wint van het `rows`-attribuut, en
bij een leeg vak is `scrollHeight` één regel plus padding — dus elk leeg
meerregelig vak opende op één regel, zó laag dat de placeholder horizontaal
doorgesneden werd. Koen zag het op Omschrijving en Interne nota.

**Dit hoort in een browser.** Een test die de tekst van de `x-init`-expressie
vergelijkt, bewijst niets over gerenderde hoogte: de hele fout zit in wat de
browser mét die expressie doet.

Drie metingen, en de derde is de tegenhanger: `rows=1` moet `rows=1` blijven.
Een harde ondergrens van drie regels zou de vraagbalk van Raakje breken om dit
te repareren.

**De reparatie bestaat uit twee delen, en elk deel heeft zijn eigen test** —
gemeten, want ik dacht eerst dat één tegenproef beide zou vangen:

* de klem `Math.max(..., bodem)` weggehaald → alleen *wissen* valt om. Het
  openen blijft goed, want zonder klem schrijft de macro nog steeds niets
  zolang het vak verborgen is.
* de regel die niets schrijft bij hoogte nul weggehaald (dus tóch meten terwijl
  het vak nog dicht zit) → alleen *openen* valt om, precies de melding van
  Koen: Omschrijving en Interne nota op één regel.

De derde test blijft in beide gevallen groen; die bewaakt dat de reparatie geen
ander scherm meesleurt.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, Activiteitdetail, login_als_admin, pagina_klaar  # noqa: E402

# Hoeveel de gemeten hoogte mag afwijken van de natuurlijke `rows`-hoogte. Eén
# pixel speling voor afronding; drie regels tegen één is een verschil van tientallen.
SPELING = 1


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
        yield page
        browser.close()


# Wat `rows` zonder inline hoogte zou opleveren: een kloon van hetzelfde veld,
# leeg, zonder `style.height`, in dezelfde pagina gemeten. Dat is de eerlijke
# maatstaf — een hardgecodeerd getal zou lettertype en padding negeren.
NATUURLIJK = """(sel) => {
  const el = document.querySelector(sel);
  const kloon = el.cloneNode(false);
  kloon.value = '';
  kloon.style.height = '';
  kloon.style.visibility = 'hidden';
  el.parentNode.appendChild(kloon);
  const hoogte = kloon.offsetHeight;
  kloon.remove();
  return hoogte;
}"""


def _open_activiteit(admin_page):
    scherm = Activiteitdetail(admin_page)
    if not scherm.open_eerste():
        _ontbreekt("geen activiteit om te openen")
    admin_page.locator('button:has-text("Bewerken")').first.click()
    pagina_klaar(admin_page)
    return scherm


def test_een_leeg_vak_opent_op_het_aantal_regels_dat_het_vroeg(admin_page):
    """Het gemelde geval: Omschrijving en Interne nota vragen allebei `rows=3`."""
    _open_activiteit(admin_page)

    for selector in ("#description", "#board_notes"):
        veld = admin_page.locator(selector)
        if veld.count() == 0:
            _ontbreekt(f"{selector} staat niet op dit scherm")
        veld.fill("")
        natuurlijk = admin_page.evaluate(NATUURLIJK, selector)
        gemeten = veld.bounding_box()["height"]

        assert gemeten >= natuurlijk - SPELING, (
            f"{selector}: {gemeten}px terwijl rows drie regels ({natuurlijk}px) "
            "vraagt — de placeholder wordt dan doorgesneden (#1037)")


def test_wissen_brengt_het_vak_niet_onder_zijn_ondergrens(admin_page):
    """Dezelfde regel staat in `x-on:input`, dus tijdens het typen geldt ze ook."""
    _open_activiteit(admin_page)
    veld = admin_page.locator("#description")
    if veld.count() == 0:
        _ontbreekt("#description staat niet op dit scherm")
    natuurlijk = admin_page.evaluate(NATUURLIJK, "#description")

    veld.fill("Een tekst die ruim over drie regels loopt. " * 25)
    gegroeid = veld.bounding_box()["height"]
    veld.fill("")
    na_wissen = veld.bounding_box()["height"]

    assert gegroeid > natuurlijk, "het vak groeit niet meer mee"
    assert na_wissen >= natuurlijk - SPELING, (
        f"na wissen {na_wissen}px, onder de ondergrens van {natuurlijk}px")


def test_een_vak_dat_een_regel_vraagt_blijft_een_regel(admin_page):
    """De tegenhanger: de vraagbalk van Raakje vraagt bewust `rows=1`.

    Zonder deze test zou "zet de ondergrens op drie regels" ook groen staan — en
    dan is het ene scherm gerepareerd ten koste van het andere. Gemeten op de
    zwevende bel: de pagina `/raakje` waar dit vroeger op stond is weg (#1120), en
    de bel draagt exact dezelfde balk.
    """
    from tests_e2e.schermen import open_de_raakje_bel

    veld = open_de_raakje_bel(admin_page)
    if veld.count() == 0:
        _ontbreekt("de vraagbalk van Raakje staat er niet")

    een_regel = admin_page.evaluate(NATUURLIJK, "#raakje-widget-vraag")
    gemeten = veld.bounding_box()["height"]

    assert gemeten <= een_regel + SPELING, (
        f"het eenregelige veld is {gemeten}px in plaats van {een_regel}px")
    assert een_regel < 50, (
        f"een 'regel' van {een_regel}px is geen regel meer — meet dit veld wel "
        "wat het denkt te meten?")
