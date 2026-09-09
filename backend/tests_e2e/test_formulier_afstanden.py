"""E2E: de drie afstanden op het publieke formulier (#768, bijgesteld in #774).

Dit is de tweede keer dat deze waarden verschuiven, en beide keren was het oordeel
optisch. Wat een test kan vastleggen is het resultaat van dat oordeel, zodat een
latere opruiming — een `space-y` die "netter" op een Tailwind-stap wordt gezet, een
padding die meelift met een andere wijziging — niet stilzwijgend de verhouding
verandert.

**Waarom de verhouding en niet de maat.** Nabijheid maakt zichtbaar welke antwoorden
bij welke vraag horen. #749 zette dat voor het eerst recht (alles stond op gelijke
afstand en de lijst las als één massa), #768 moest het opnieuw doen toen de trefzone
naar 40 px ging, en #774 heeft het strakker gezet: 16 : 20 : 30 px, dus stappen van
1,25× en 1,5×.

**De tweede test is de tegenproef die ertoe doet.** Het wit tussen twee antwoorden is
de padding ín het klikvlak, geen gat ertussen. Een test op de hoogte alleen staat ook
groen wanneer er 16 px niemandsland tussen de trefzones zit — en dan doet een tik op
die strook niets. De trefzones moeten elkaar raken: geen gat, en ook geen overlap,
want in een overlap wint de onderste rij.

De foutmarkering uit #741 staat in `test_formulier_wizard_stap.py`.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `py-2` van het
optielabel weggehaald, en apart daarvan `space-y-1` terug op de optiegroep. Beide keren
vallen **beide** tests om — de afstanden kloppen niet meer én de trefzones raken elkaar
niet meer. Dat ze samen omvallen is geen dubbeling: bij `space-y-1` faalt de tweede op
een gat van 4 px waar de eerste alleen ziet dat het wit niet meer klopt.
"""
import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE  # noqa: E402

# Verwacht wit, in pixels: tussen twee antwoorden, tussen de vraag en haar eerste
# antwoord, en tussen het laatste antwoord en de volgende vraag.
TUSSEN_ANTWOORDEN = 16
VRAAG_NAAR_ANTWOORD = 20
NAAR_VOLGENDE_VRAAG = 30

METEN = """() => {
  const r = (e) => e.getBoundingClientRect();
  const blok = document.querySelectorAll('[data-veld]');
  const vraag1 = blok[0].querySelector('label');
  const opties = [...blok[0].querySelectorAll(':scope > div > label')];
  const vraag2 = blok[1].querySelector('label');
  const stijl = getComputedStyle(opties[0]);
  return {
    opties: opties.length,
    hoogte: Math.round(r(opties[0]).height),
    padding: Math.round(parseFloat(stijl.paddingTop)),
    // doos-afstanden: tussen de klikvlakken zelf
    doos_tussen: opties.slice(1).map((o, i) => Math.round(r(o).top - r(opties[i]).bottom)),
    doos_vraag: Math.round(r(opties[0]).top - r(vraag1).bottom),
    doos_volgende: Math.round(r(vraag2).top - r(opties[opties.length - 1]).bottom),
  };
}"""


@pytest.fixture(scope="module")
def formulier():
    """Eén sectie, twee vragen met opties — genoeg voor alle drie de afstanden."""
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.forms.models import (Form, FormField, FormFieldOption,
                                          FormSection)

    db = SessionLocal()
    token = "e2e774-" + secrets.token_urlsafe(6)
    form = Form(title="E2E Afstanden", status="open", is_anonymous=True,
                share_token=token)
    db.add(form)
    db.flush()
    sec = FormSection(form_id=form.id, title="Over de activiteit", position=0)
    db.add(sec)
    db.flush()
    for pos, (label, soort, opties) in enumerate((
        ("Hoe heb je het ervaren?", "radio", ("Heel goed", "Goed", "Matig")),
        ("Wat nam je mee?", "checkbox", ("Regenjas", "Verrekijker")),
    )):
        veld = FormField(form_id=form.id, section_id=sec.id, label=label,
                         field_type=soort, position=pos)
        db.add(veld)
        db.flush()
        for i, tekst in enumerate(opties):
            db.add(FormFieldOption(field_id=veld.id, label=tekst, position=i))
    db.commit()
    db.close()
    return token


@pytest.fixture(scope="module")
def meting(formulier):
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(viewport={"width": 760, "height": 1100})
        page.goto(f"{BASE}/formulier/{formulier}")
        page.wait_for_selector("[data-veld]")
        uit = page.evaluate(METEN)
        browser.close()
    return uit


def test_de_drie_afstanden_staan_op_16_20_en_30(meting):
    """Het wit dat je ziet is de doos-afstand plus de padding van het klikvlak."""
    assert meting["opties"] == 3, "de meting kijkt niet naar de eerste vraag"
    p = meting["padding"]

    wit_tussen = [d + 2 * p for d in meting["doos_tussen"]]
    assert wit_tussen == [TUSSEN_ANTWOORDEN] * len(wit_tussen), (
        f"tussen twee antwoorden staat {wit_tussen} px wit i.p.v. {TUSSEN_ANTWOORDEN}")
    assert meting["doos_vraag"] + p == VRAAG_NAAR_ANTWOORD, (
        f"tussen de vraag en haar eerste antwoord staat {meting['doos_vraag'] + p} px "
        f"wit i.p.v. {VRAAG_NAAR_ANTWOORD}")
    assert meting["doos_volgende"] + p == NAAR_VOLGENDE_VRAAG, (
        f"tussen het laatste antwoord en de volgende vraag staat "
        f"{meting['doos_volgende'] + p} px wit i.p.v. {NAAR_VOLGENDE_VRAAG}")


def test_de_trefzones_raken_elkaar(meting):
    """Geen dode strook tussen twee antwoorden, en geen overlap.

    Dit is wat een test op de hoogte alleen niet ziet: 36 px hoge klikvlakken met
    16 px ruimte ertussen halen dezelfde hoogtemeting, en dan doet een tik tussen
    twee antwoorden niets — precies het gat dat #768 wegnam.
    """
    assert meting["doos_tussen"] == [0] * len(meting["doos_tussen"]), (
        f"er zit {meting['doos_tussen']} px tussen de klikvlakken; negatief is een "
        "overlap (dan wint de onderste rij), positief is een dode zone")
    assert meting["hoogte"] >= 32, (
        f"een trefzone van {meting['hoogte']} px is te krap voor een vinger")
