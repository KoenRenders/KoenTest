"""E2E: the public header's band and the logo in it (#1156, #1588).

#1156 traded the band's padding for logo height. CR-11 pilot B (#1588, decision
11) fixed the band itself: 64 px on a phone, 80 px at 1 440 (112 at 768, in two
rows — `test_public_shell.py`), and the logo one image of 48 px at every width.
What #1156 asked still holds and is measured here in a browser, because this is
layout:

- the band has its height WITH a logo, and the same height WITHOUT one — a logo
  never makes the header taller;
- the logo is 48 px high and fits the lowest band with air above and under it;
  on a phone that is still more than the 40 px it had before #1156;
- the menu button keeps its 44 px (#804).

Proven red (measured, on this branch): the logo's CSS height set to 72 px → the
logo test fails (it no longer fits the band, whose height is the grid's); the
menu button's `w-11 h-11` removed → the touch-target test fails.
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

BREED = {"width": 1440, "height": 900}
TELEFOON = {"width": 390, "height": 844}

# The band's heights (#1588) and the logo's one height.
BALK = {"breed": 80.0, "telefoon": 64.0}
LOGO = 48.0
# What a phone showed before #1156: the logo may never fall back to it.
OUD_LOGO_TELEFOON = 40.0
AANRAAKVLAK = 44.0  # #804: de ondergrens voor een vinger


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
    the proof that the logo is there, at its one height, and fits the band."""
    for naam, viewport in (("breed", BREED), ("telefoon", TELEFOON)):
        balk = _kopbalk(page, viewport)
        logo = page.locator("header img").first
        expect(logo, "de kopbalk toont geen logo; dan meet deze test niets").to_be_visible()
        vak = logo.bounding_box()

        assert abs(vak["height"] - LOGO) <= 1, f"het logo is op {naam} {vak['height']:.0f}px"
        # Inside the band, with at least 8 px above and under it.
        assert (
            vak["y"] - balk["y"] >= 7
            and (balk["y"] + balk["height"]) - (vak["y"] + vak["height"]) >= 7
        ), f"het logo ({vak}) past niet in de balk ({balk}) op {naam}"
    assert LOGO > OUD_LOGO_TELEFOON


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
