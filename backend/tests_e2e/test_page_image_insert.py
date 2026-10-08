"""E2E #1173: de knop voegt een afbeelding in, en ze staat op de pagina.

**Waarom dit in een echte browser moet.** `tests/integration/test_page_image_1173.py`
toetst de serverhelft op een vastgelegd document — maar zo'n constante veroudert
stil. Deze test klikt de échte knop in de échte editor, vult de échte dialoog en
kijkt wat er in de verborgen invoer belandt. Twee beweringen, en de eerste is de
belangrijkste:

1. De dialoog bewaart de figuur **met de alt en de media-id in het document**.
   Dat is precies de aanname waar de serverhelft op rust. Klopt ze niet meer,
   dan faalt hier de assert met het werkelijke document in de melding.
2. Na opslaan én publiceren staat op de pagina een `<img>` met die alt — de weg
   langs de opslagadapter, de validatie en de sanitatie, van klik tot site.

**Slepen van een bestand blijft geweigerd** (#1173's eigen regel): de editor
heeft geen upload en geen afbeeldings-dropper — een bestand dat op haar
neerkomt verandert het document niet. Wie een nieuwe afbeelding wil, laadt
die eerst op bij Media en kiest haar in de dialoog.

Snede 3 (#1671): de figuur komt uit de kit's kiezer in de dialoog van de
`ui.document_editor` macro; de alt start op de titel en blijft verplicht.
"""

import io
import os
import re
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (  # noqa: E402
    BASE,
    Paginascherm,
    htmx_afgerond,
    login_met_sessie,
    pagina_klaar,
)

PICKER = "#mp-cp-document-figuur"


def _foto() -> tuple[int, str]:
    """A picture with real bytes, so the browser really loads it."""
    from PIL import Image

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.media.models import MediaAsset

    buf = io.BytesIO()
    Image.new("RGB", (320, 200), (40, 90, 130)).save(buf, format="PNG")
    png = buf.getvalue()
    title = f"Uitleg afbeelding {secrets.token_hex(2)}"
    db = SessionLocal()
    try:
        asset = MediaAsset(
            kind="page_image",
            title=title,
            data=png,
            content_type="image/png",
            thumbnail=png,
            thumb_content_type="image/png",
            width=320,
            height=200,
            byte_size=len(png),
            sort_order=0,
            is_active=True,
        )
        db.add(asset)
        db.commit()
        return asset.id, title
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    photo = _foto()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), photo
        b.close()


def _open_en_kies(setup, alt: str):
    b, session, (photo_id, title) = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    login_met_sessie(page, session)
    scherm = Paginascherm(page).open_eerste()
    if scherm is None:
        pytest.fail("e2e-seed geladen maar: geen cms-pagina")
    page.locator("#cp-document details summary").click()
    page.locator("#cp-document details button", has_text="Afbeelding").click()
    dialoog = page.get_by_role("dialog")
    expect(dialoog).to_be_visible()
    dialoog.locator(f"{PICKER} button[data-url]").first.wait_for()
    pagina_klaar(page)
    dialoog.locator(f"button[data-id='{photo_id}']").click()
    if alt is not None:
        dialoog.locator("#cp-document-fig-alt").fill(alt)
    return page, scherm, dialoog


def test_de_knop_voegt_een_afbeelding_met_alt_in(setup):
    """The real button, the real dialog: the figure stands in the editor's
    document with her alt, and after save and publish on the page."""
    b, session, (photo_id, title) = setup
    alt = f"Schermtest {secrets.token_hex(2)}"
    page, scherm, dialoog = _open_en_kies(setup, alt)

    dialoog.get_by_role("button", name="Invoegen").click()
    document = scherm.editorinhoud()
    print("MEASURE document after insert", document[:200])
    assert f'"media_id":{photo_id}' in document.replace(" ", ""), (
        "de figuur staat niet met haar media-id in het document"
    )
    assert f'"{alt}"' in document, "de alt staat niet in het document"

    scherm.opslaan()
    pagina_klaar(page)
    page_id = re.search(r"/admin/paginas/(\d+)", page.url).group(1)
    with htmx_afgerond(page):
        page.get_by_role("button", name="Publiceren").first.click()
    pagina_klaar(page)
    page.goto(f"/admin/paginas/{page_id}/voorbeeld")
    beeld = page.locator(f"img[src='/api/v1/media/{photo_id}']")
    expect(beeld).to_have_count(1)
    assert beeld.first.get_attribute("alt") == alt, "de alt is niet op de pagina beland"
    loaded = page.evaluate("el => el.complete && el.naturalWidth", beeld.element_handle())
    print("MEASURE naturalWidth", loaded)
    assert loaded == 320, "de afbeelding staat er maar laadt niet"
    page.close()


def test_slepen_van_een_bestand_blijft_geweigerd(setup):
    """#1173's deliberate refusal: a file dropped on the editor changes
    nothing — there is no upload path, so no data-URI can land in the
    document. Red the day a drop handler smuggles one in: the document
    would change."""
    b, session, (_photo_id, _title) = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    login_met_sessie(page, session)
    scherm = Paginascherm(page).open_eerste()
    voor = scherm.editorinhoud()

    veranderd = page.evaluate(
        """() => { const tip = document.querySelector('.tiptap');
          const mount = document.querySelector('[data-document-editor]');
          const bytes = new Uint8Array([137, 80, 78, 71]);  // a PNG's first bytes
          const bestand = new File([bytes], 'gestort.png', {type: 'image/png'});
          const dt = new DataTransfer(); dt.items.add(bestand);
          tip.dispatchEvent(new DragEvent('drop', {bubbles: true, dataTransfer: dt}));
          return document.getElementById(mount.dataset.input).value; }"""
    )
    print("MEASURE document after drop", veranderd[:120])
    assert veranderd == voor, (
        "een neergesleept bestand veranderde het document — de editor heeft een uploadpad gekregen"
    )
    assert "data:" not in veranderd, "er staat een data-URI in het document"
    page.close()
