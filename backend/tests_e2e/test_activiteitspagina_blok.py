"""E2E: tekst en affiche staan als één blok in het midden (#1143).

Koen zag op de Bowlen-pagina een leeg vlak van ruwweg een derde van de breedte
tussen zijn tekst en de affiche. De oorzaak was de kolom: die was `flex-1` en nam
alle overblijvende ruimte, terwijl de tekst stopt bij de leesbreedte.

**Dit is opmaak, dus het bewijs is een meting in een browser.** De servertest
(`tests/test_activiteitspagina_blok_1143.py`) legt de afleiding vast — de breedte
van het blok is de som van drie maten die elk ook elders gebruikt worden. Of die
som op het scherm ook echt gelijke marges oplevert, ziet alleen een browser: die
rekent `calc()` uit, past de mediaquery toe en legt de kolommen naast elkaar.

Drie metingen, en de derde is er omdat 80% van het bezoek mobiel is: daar hoort
niets veranderd te zijn.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten): de
`md:max-w-[calc(...)]` van de rij weggehaald → de linkerkolom neemt weer alle
ruimte, het blok schuift naar links en de marges lopen tientallen pixels uiteen.
"""
import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402
from tests_e2e.test_beheer_flows import _ontbreekt  # noqa: E402

BREED = {"width": 1440, "height": 900}
TELEFOON = {"width": 390, "height": 844}


@pytest.fixture(scope="module")
def activiteit_met_affiche():
    """Een publieke activiteit mét affiche, rechtstreeks in de databank.

    Dezelfde weg als `seeded_activities` in de golden flows: de e2e-backend praat
    tegen dezelfde databank, en zo blijft de gedeelde seed ongemoeid.
    """
    from datetime import date, timedelta
    from decimal import Decimal

    import app.models  # noqa: F401  → alle mappers geconfigureerd
    from app.database import SessionLocal
    from app.domains.activities.api import (Activity, ActivityDate,
                                            ActivitySubRegistration)
    from app.domains.media.api import MediaAsset

    db = SessionLocal()
    try:
        a = Activity(name="E2E Blokproef",
                     description="Een korte omschrijving van deze activiteit.")
        db.add(a)
        db.flush()
        db.add(ActivityDate(activity_id=a.id,
                            start_date=date.today() + timedelta(days=21)))
        db.add(ActivitySubRegistration(activity_id=a.id, name="Deelname",
                                       price=Decimal("0"), is_free=True))
        # Een echt PNG'je van één pixel: de pagina toont het als affiche.
        db.add(MediaAsset(
            kind="activity_poster", activity_id=a.id, title="Affiche",
            content_type="image/png",
            data=bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000"
                "001f15c4890000000a49444154789c6360000002000100ffff03000006"
                "0005a5f7b6e40000000049454e44ae426082")))
        db.commit()
        return a.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE, viewport=BREED)
        yield p
        browser.close()


def _rij(page):
    """De rij met de twee kolommen: de ouder van de affichekolom.

    Niet op de klasse zoeken: de schil draagt ook `md:flex`-elementen (de
    kopbalk), en die staan eerder in de DOM. De `<aside>` is uniek op deze
    pagina, dus haar ouder is de rij — en die blijft kloppen als de klassen
    veranderen, wat hier nu juist het onderwerp is.
    """
    rij = page.locator("aside").locator("xpath=..")
    expect(rij, "de rij met de twee kolommen staat er niet").to_be_visible()
    return rij


def test_op_een_breed_scherm_staat_het_blok_gecentreerd(page, activiteit_met_affiche):
    """De meting uit het issue: de ruimte links en rechts is gelijk."""
    page.set_viewport_size(BREED)
    page.goto(f"/activiteiten/{activiteit_met_affiche}")
    pagina_klaar(page)

    if page.locator("aside img").count() == 0:
        _ontbreekt("deze activiteit toont geen affiche")

    blok = _rij(page).bounding_box()
    schil = page.locator("main").bounding_box()
    links = blok["x"] - schil["x"]
    rechts = (schil["x"] + schil["width"]) - (blok["x"] + blok["width"])

    assert abs(links - rechts) <= 2, (
        f"het blok staat niet in het midden: {links:.0f}px links, {rechts:.0f}px rechts")
    # En het blok is ook echt smaller dan de schil. Zonder deze regel zou de test
    # óók groen staan in de oude situatie: een blok dat de volle breedte vult,
    # heeft immers links en rechts evenveel ruimte — namelijk de 16px van de
    # schilmarge. Gemeten tijdens de tegenproef, en dat is precies waarom ze
    # erbij staat.
    assert schil["width"] - blok["width"] >= 100, (
        f"het blok vult de volle breedte ({blok['width']:.0f} van "
        f"{schil['width']:.0f}px); dan is er niets gecentreerd")
    assert links > 40, f"maar {links:.0f}px ruimte naast het blok"


def test_de_affiche_sluit_aan_op_de_tekst(page, activiteit_met_affiche):
    """Waar Koen naar keek: het gat tussen het einde van de tekst en de affiche.

    De tussenruimte is `gap-8` (2rem = 32px). Meer dan dat betekent dat de
    linkerkolom weer doorloopt waar de tekst ophoudt.
    """
    page.set_viewport_size(BREED)
    page.goto(f"/activiteiten/{activiteit_met_affiche}")
    pagina_klaar(page)

    omschrijving = page.locator("div.whitespace-pre-line").first
    affiche = page.locator("aside").first
    if affiche.count() == 0:
        _ontbreekt("deze activiteit toont geen affiche")

    tekst = omschrijving.bounding_box()
    beeld = affiche.bounding_box()
    gat = beeld["x"] - (tekst["x"] + tekst["width"])

    assert gat <= 40, (
        f"er zit {gat:.0f}px tussen de tekst en de affiche; de kolom loopt door "
        "waar de tekst ophoudt (#1143)")


def test_op_een_telefoon_staat_de_affiche_boven_de_tekst(page, activiteit_met_affiche):
    """80% van het bezoek is mobiel: daar hoort niets veranderd te zijn."""
    page.set_viewport_size(TELEFOON)
    page.goto(f"/activiteiten/{activiteit_met_affiche}")
    pagina_klaar(page)

    expect(page.locator("aside"), "de rechterkolom hoort op een telefoon weg").to_be_hidden()

    beeld = page.locator("a[target='_blank'] img").first
    omschrijving = page.locator("div.whitespace-pre-line").first
    expect(beeld, "de affiche staat niet op de telefoonweergave").to_be_visible()
    assert beeld.bounding_box()["y"] < omschrijving.bounding_box()["y"], (
        "de affiche staat niet meer boven de omschrijving")
