"""E2E: de kopbalk ruilt padding in voor logohoogte (#1156).

Koen vroeg tijdens zijn HDEV-ronde hoeveel groter het logo kon zonder de balk
hoger te maken. Een deel van de kleinheid zat in het bestand (dat snijdt hij zelf
bij), een deel in de balk: de padding nam ruimte die het logo niet kreeg.

**Dit is opmaak, dus het bewijs is een meting in een browser.** Hier staan de
hoogtes die de browser écht rendert, niet de klassen die ze zouden moeten
opleveren — een test op `py-2` staat ook groen als de balk intussen door iets
anders hoger wordt.

De vier waarden hieronder zijn gemeten op 21 september 2026, vóór de wijziging,
op deze pagina met een logo in de media:

    breed (1440)  balk 80 px, logo 48 px
    telefoon (390) balk 76 px, logo 40 px, menuknop 44 px

Dat de balk even hoog blijft, is de eis. Maar die eis slaagt óók als er niets
gebeurt — daarom staat er een aparte test op dát het logo gegroeid is, met de
oude hoogtes als ondergrens.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
`--lucht` terug op 16px → het logo zakt naar 48/40 en `test_het_logo_is_groter`
valt om op beide breedtes; `min-w-11 min-h-11` van de menuknop vervangen door de
padding-variabele → `test_het_aanraakvlak_blijft` valt om op 16 px.
"""
import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

BREED = {"width": 1440, "height": 900}
TELEFOON = {"width": 390, "height": 844}

# Gemeten vóór de wijziging. De balk mag niet veranderen; het logo moet erboven.
BALK = {"breed": 80.0, "telefoon": 76.0}
OUD_LOGO = {"breed": 48.0, "telefoon": 40.0}
AANRAAKVLAK = 44.0          # #804: de ondergrens voor een vinger
BALK_ZONDER_LOGO = {"breed": 71.0, "telefoon": 76.0}


def _logo_bytes() -> bytes:
    """Een echt PNG'je van 300 × 100: `w-auto` leidt de breedte uit de hoogte af,
    dus de verhouding moet realistisch zijn of de meting zegt niets."""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (300, 100), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def logo_in_de_kopbalk():
    """Zet een verenigingslogo klaar en ruim het daarna weer op.

    Opruimen hoort erbij: dit logo verschijnt op élke publieke pagina, dus zonder
    teardown zou een volgend testbestand een andere kopbalk zien dan het verwacht.
    """
    import app.models  # noqa: F401  → alle mappers geconfigureerd
    from app.database import SessionLocal
    from app.domains.media.api import MediaAsset

    db = SessionLocal()
    try:
        asset = MediaAsset(kind="tenant_logo", title="Logo voor de meting",
                           content_type="image/png", data=_logo_bytes())
        db.add(asset)
        db.commit()
        nummer = asset.id
    finally:
        db.close()

    yield nummer

    db = SessionLocal()
    try:
        db.query(MediaAsset).filter(MediaAsset.id == nummer).delete()
        db.commit()
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


def _kopbalk(page, viewport):
    """De rij met het logo en de navigatie, op de gevraagde breedte."""
    page.set_viewport_size(viewport)
    page.goto("/")
    pagina_klaar(page)
    rij = page.locator("header nav > div").first
    expect(rij, "de kopbalk staat er niet").to_be_visible()
    return rij.bounding_box()


def test_de_balk_blijft_even_hoog(page, logo_in_de_kopbalk):
    """De eis uit het issue: op beide breedtes exact de hoogte van vandaag."""
    for naam, viewport in (("breed", BREED), ("telefoon", TELEFOON)):
        hoogte = _kopbalk(page, viewport)["height"]
        assert abs(hoogte - BALK[naam]) <= 1, (
            f"de kopbalk is op {naam} {hoogte:.0f}px geworden in plaats van "
            f"{BALK[naam]:.0f}px (#1156)")


def test_het_logo_is_groter(page, logo_in_de_kopbalk):
    """Zonder deze test slaagt de vorige ook als er niets gebeurt.

    De balk even hoog laten is immers gratis: dat is de toestand van vandaag.
    Wat bewezen moet worden is de rúil — het logo krijgt de ruimte die de
    padding afstaat.
    """
    for naam, viewport in (("breed", BREED), ("telefoon", TELEFOON)):
        balk = _kopbalk(page, viewport)
        logo = page.locator("header img").first
        expect(logo, "de kopbalk toont geen logo; dan meet deze test niets").to_be_visible()
        hoogte = logo.bounding_box()["height"]

        assert hoogte > OUD_LOGO[naam], (
            f"het logo is op {naam} niet gegroeid: {hoogte:.0f}px, was "
            f"{OUD_LOGO[naam]:.0f}px (#1156)")
        # En het is de balk die de ruimte geeft: wat overblijft na de padding
        # boven en onder. Gemeten 64px breed en 60px op een telefoon.
        assert abs(hoogte - (balk["height"] - 16)) <= 1, (
            f"het logo ({hoogte:.0f}px) vult de balk ({balk['height']:.0f}px) niet "
            "tot op de padding na; dan is de hoogte niet meer afgeleid")


def test_het_aanraakvlak_van_de_menuknop_blijft(page, logo_in_de_kopbalk):
    """#804: 44px is de ondergrens voor een vinger en mag niet meekrimpen.

    De menuknop staat in dezelfde rij als het logo, dus een padding die kleiner
    wordt mag haar niet meenemen.
    """
    _kopbalk(page, TELEFOON)
    knop = page.locator("header button[aria-label]").first
    expect(knop, "de menuknop staat er niet op telefoonbreedte").to_be_visible()

    vlak = knop.bounding_box()
    assert vlak["height"] >= AANRAAKVLAK, (
        f"het aanraakvlak is {vlak['height']:.0f}px hoog geworden; onder de "
        f"{AANRAAKVLAK:.0f}px van #804")
    assert vlak["width"] >= AANRAAKVLAK, (
        f"het aanraakvlak is {vlak['width']:.0f}px breed geworden; onder de "
        f"{AANRAAKVLAK:.0f}px van #804")


def test_zonder_logo_blijft_de_kopbalk_zoals_ze_was(page, logo_in_de_kopbalk):
    """De woordmerk-tak valt buiten dit issue en mag dus niet verschuiven.

    De padding draagt beide takken. Gemeten zonder logo: 71px breed (woordmerk 39
    + 2 × 16) en 76px op een telefoon (menuknop 44 + 2 × 16). Zou de padding daar
    mee krimpen, dan zakte die balk naar 55px.

    Het logo gaat hier even weg en komt daarna terug, zodat de rest van dit
    bestand blijft meten wat het denkt te meten.
    """
    from app.database import SessionLocal
    from app.domains.media.api import MediaAsset

    db = SessionLocal()
    try:
        asset = db.query(MediaAsset).filter(MediaAsset.id == logo_in_de_kopbalk).one()
        bewaard = (asset.kind, asset.data)
        # `component_info` en niet een verzonnen naam: de databank heeft een
        # CHECK op `kind` (gemeten — ze weigerde de verzonnen soort), en deze
        # soort komt in de publieke kopbalk niet voor.
        asset.kind = "component_info"
        db.commit()
    finally:
        db.close()

    try:
        for naam, viewport in (("breed", BREED), ("telefoon", TELEFOON)):
            balk = _kopbalk(page, viewport)
            assert page.locator("header img").count() == 0, "er staat toch een logo"
            assert abs(balk["height"] - BALK_ZONDER_LOGO[naam]) <= 1, (
                f"de woordmerk-balk is op {naam} {balk['height']:.0f}px geworden in "
                f"plaats van {BALK_ZONDER_LOGO[naam]:.0f}px; die tak hoort niet mee "
                "te veranderen (#1156)")
    finally:
        db = SessionLocal()
        try:
            asset = db.query(MediaAsset).filter(MediaAsset.id == logo_in_de_kopbalk).one()
            asset.kind = bewaard[0]
            db.commit()
        finally:
            db.close()
