"""E2E: the public header's band and the logo in it (#1156, #1588).

#1156 traded the band's padding for logo height. CR-11 pilot B (#1588, decision
11) fixed the band itself: 64 px on a phone, 80 px at 1 440 (112 at 768, in two
rows — `test_public_shell.py`). What #1156 asked is measured here in a browser,
because this is layout:

- the band has its height WITH a logo, and the same height WITHOUT one — a logo
  never makes the header taller;
- the logo is as high as its row allows, the row minus 2 × 8 px (#1621): 48 px
  on a phone and at 768 (the first row of 64), 64 px at 1 440 (the band of 80),
  with exactly 8 px above and under it;
- a very wide logo is drawn inside its box and leaves the menu button its
  44 px, inside the window;
- the menu button keeps its 44 px (#804).

**What this file asserted while the logo shrank (#1621).** #1588 set the logo
to 48 px at every width and rewrote this file to say so; the only floor left
was "more than the 40 px a phone had before #1156". v2.12.0 showed 64 px on a
desktop, and nothing here compared the logo with its row. Now the height is
the row's minus 16 px at each width. Red against master `3f1525a2`: 48 px at
1 440 where 64 is expected.

Proven red (measured, on this branch): the 64 px rule removed → the logo test
fails at 1 440 (and set to 56 px: fails with "56.0px"); the logo forbidden to
shrink (`max-width:none;flex-shrink:0`) → the wide-logo test fails at 390, its
box 576 px wide over the button (removing `max-width:100%` alone does NOT turn
it red: the brand's flex box shrinks the image as well); the menu button's `w-11 h-11` removed → the touch-target test fails.
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

BREED = {"width": 1440, "height": 900}
TABLET = {"width": 768, "height": 1024}
TELEFOON = {"width": 390, "height": 844}

# The band's heights (#1588) and the logo's height per width (#1621): the row
# the logo stands in, minus 2 × 8 px.
BALK = {"breed": 80.0, "telefoon": 64.0}
RIJ = {"breed": 80.0, "tablet": 64.0, "telefoon": 64.0}
LUCHT = 8.0
# What a phone showed before #1156: the logo may never fall back to it.
OUD_LOGO_TELEFOON = 40.0
AANRAAKVLAK = 44.0  # #804: de ondergrens voor een vinger


def _logo_bytes(width: int = 300, height: int = 100) -> bytes:
    """Een echt PNG'je van 300 × 100: `w-auto` leidt de breedte uit de hoogte af,
    dus de verhouding moet realistisch zijn of de meting zegt niets."""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (width, height), (255, 255, 255)).save(buf, format="PNG")
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
        asset = MediaAsset(
            kind="tenant_logo",
            title="Logo voor de meting",
            content_type="image/png",
            data=_logo_bytes(),
        )
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
    rij = page.locator("header.site-header").first
    expect(rij, "de kopbalk staat er niet").to_be_visible()
    return rij.bounding_box()


def test_de_balk_blijft_even_hoog(page, logo_in_de_kopbalk):
    """With a logo the band has exactly its height, at both widths."""
    for naam, viewport in (("breed", BREED), ("telefoon", TELEFOON)):
        hoogte = _kopbalk(page, viewport)["height"]
        assert abs(hoogte - BALK[naam]) <= 1, (
            f"de kopbalk is op {naam} {hoogte:.0f}px geworden in plaats van "
            f"{BALK[naam]:.0f}px (#1156)"
        )


def test_het_logo_is_groter(page, logo_in_de_kopbalk):
    """The band keeping its height is free when nothing shows a logo: this is
    the proof that the logo is there and takes what its row gives (#1621) —
    the row minus 2 × 8 px, with exactly that air above and under it, and in
    the image's own proportions."""
    gemeten = {}
    for naam, viewport in (("breed", BREED), ("tablet", TABLET), ("telefoon", TELEFOON)):
        balk = _kopbalk(page, viewport)
        logo = page.locator("header img").first
        expect(logo, "de kopbalk toont geen logo; dan meet deze test niets").to_be_visible()
        vak = logo.bounding_box()
        gemeten[naam] = vak["height"]

        verwacht = RIJ[naam] - 2 * LUCHT
        assert abs(vak["height"] - verwacht) <= 0.5, (
            f"het logo is op {naam} {vak['height']:.1f}px; de rij van {RIJ[naam]:.0f}px "
            f"laat {verwacht:.0f}px toe (#1621)"
        )
        # 8 px above it, and 8 px under it to the end of its ROW (at 768 the
        # band has a second row under the logo's).
        boven = vak["y"] - balk["y"]
        onder = (balk["y"] + RIJ[naam]) - (vak["y"] + vak["height"])
        assert abs(boven - LUCHT) <= 0.5 and abs(onder - LUCHT) <= 0.5, (
            f"de lucht rond het logo is op {naam} {boven:.1f} en {onder:.1f}px"
        )
        # 300 × 100: the width follows the image.
        assert abs(vak["width"] - 3 * vak["height"]) <= 1, f"het logo is vervormd op {naam}: {vak}"
    print("MEASURE logo heights", gemeten)
    assert gemeten["telefoon"] > OUD_LOGO_TELEFOON


def test_een_heel_breed_logo_duwt_de_menuknop_niet_weg(page, logo_in_de_kopbalk):
    """#1621: a logo of 1 200 × 100 at 390 px. Its box stays inside the brand's
    column, the menu button keeps its 44 px inside the window, the band keeps
    its height and the page does not scroll sideways. (v2.12.0 squeezed the
    button to 21 px with such a logo — measured.)"""
    from app.database import SessionLocal
    from app.domains.media.api import MediaAsset

    # An asset of its own: the browser keeps the picture at the other
    # address, so new bytes there would never be drawn.
    db = SessionLocal()
    try:
        db.query(MediaAsset).filter(MediaAsset.id == logo_in_de_kopbalk).update(
            {"kind": "component_info"}
        )
        breed = MediaAsset(
            kind="tenant_logo",
            title="Breed logo voor de meting",
            content_type="image/png",
            data=_logo_bytes(1200, 100),
        )
        db.add(breed)
        db.commit()
        breed_id = breed.id
    finally:
        db.close()
    try:
        balk = _kopbalk(page, TELEFOON)
        page.wait_for_function(
            "() => { const i = document.querySelector('header img');"
            " return i.complete && i.naturalWidth === 1200; }"
        )
        logo = page.locator("header img").first.bounding_box()
        knop = page.locator("header [data-menu-button]").first.bounding_box()
        assert abs(balk["height"] - BALK["telefoon"]) <= 1, f"de balk is {balk['height']}px"
        assert knop["width"] >= AANRAAKVLAK and knop["height"] >= AANRAAKVLAK, f"de knop: {knop}"
        assert knop["x"] + knop["width"] <= TELEFOON["width"], f"de knop valt buiten beeld: {knop}"
        assert logo["x"] + logo["width"] <= knop["x"], f"het logo ({logo}) raakt de knop ({knop})"
        assert page.evaluate("document.documentElement.scrollWidth") == TELEFOON["width"]
    finally:
        db = SessionLocal()
        try:
            db.query(MediaAsset).filter(MediaAsset.id == breed_id).delete()
            db.query(MediaAsset).filter(MediaAsset.id == logo_in_de_kopbalk).update(
                {"kind": "tenant_logo"}
            )
            db.commit()
        finally:
            db.close()


def test_het_aanraakvlak_van_de_menuknop_blijft(page, logo_in_de_kopbalk):
    """#804: 44px is de ondergrens voor een vinger en mag niet meekrimpen.

    De menuknop staat in dezelfde rij als het logo, dus een padding die kleiner
    wordt mag haar niet meenemen.
    """
    _kopbalk(page, TELEFOON)
    knop = page.locator("header [data-menu-button]").first
    expect(knop, "de menuknop staat er niet op telefoonbreedte").to_be_visible()

    vlak = knop.bounding_box()
    assert vlak["height"] >= AANRAAKVLAK, (
        f"het aanraakvlak is {vlak['height']:.0f}px hoog geworden; onder de "
        f"{AANRAAKVLAK:.0f}px van #804"
    )
    assert vlak["width"] >= AANRAAKVLAK, (
        f"het aanraakvlak is {vlak['width']:.0f}px breed geworden; onder de "
        f"{AANRAAKVLAK:.0f}px van #804"
    )


def test_zonder_logo_blijft_de_kopbalk_zoals_ze_was(page, logo_in_de_kopbalk):
    """Without a logo the header shows the tenant's name, and the band is the
    same height as with one (#1588: the band's height is the grid's, not the
    content's).

    The logo leaves for a moment and comes back, so the rest of this file keeps
    measuring what it thinks it measures.
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
            assert abs(balk["height"] - BALK[naam]) <= 1, (
                f"zonder logo is de balk op {naam} {balk['height']:.0f}px in plaats van "
                f"{BALK[naam]:.0f}px"
            )
    finally:
        db = SessionLocal()
        try:
            asset = db.query(MediaAsset).filter(MediaAsset.id == logo_in_de_kopbalk).one()
            asset.kind = bewaard[0]
            db.commit()
        finally:
            db.close()
