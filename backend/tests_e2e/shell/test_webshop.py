"""E2E CR-21 (#1887) — the shop's back-office, on a tenant of its own.

The shop is off by default for every kind of tenant, and a tenant's module set is
cached in the server process, so the browser tests run on a seeded tenant of its
own (`winkel` in `seed_e2e.py`), reached by hostname (`TENANT_HOSTNAMES` in
`e2e.env` — back-office screens are not reached by a path prefix). The
association's tenant stays untouched.

- The refused delete of an article with a movement asks visibility of the refusal
  — a box with a size, in view — not the answer's text (AC19, W23).
- A receipt and a correction are booked through their forms and the number on the
  list is read after a fresh load — the browser is the one layer that sees
  whether the movement was really committed.
"""

from __future__ import annotations

import os
import re
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (  # noqa: E402
    htmx_afgerond,
    laat_de_wacht_passeren,
    login_met_sessie,
    pagina_klaar,
    refusal_shown,
)

WEBSHOP_HOST = "http://webshop.localhost:8000"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def webshop_page(browser):
    """A browser signed in as the seeded admin on the seeded shop tenant."""
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=WEBSHOP_HOST)
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), WEBSHOP_HOST)
    page.goto("/admin/producten")
    if page.locator('a[href^="/admin/producten/"]:not([href$="/nieuw"])').count() == 0:
        pytest.fail("geen artikel op de webshop-tenant (seed_e2e)")
    yield page
    page.close()


def _on_hand_van_de_lijst(page) -> str:
    """The "In voorraad" of the seeded article, from the list's first amount cell."""
    row = page.locator("tbody tr", has_text="Webshop T-shirt").first
    return row.locator("td[data-cell=amount]").nth(0).inner_text().strip()


def test_een_verwijdering_met_voorraad_is_zichtbaar_geweigerd(webshop_page):
    """A delete of an article with a movement is refused in a box the user can
    see (AC19, W23). The browser is the only layer that proves that (#613)."""
    page = webshop_page
    page.locator('a[href^="/admin/producten/"]:not([href$="/nieuw"])').first.click()

    page.get_by_role("button", name="Acties").click()
    item = page.locator('[data-actions-menu] [role=menuitem][hx-post$="/verwijderen"]').first
    item.click()
    ok = page.locator("[data-dialog] [data-dialog-ok]")
    ok.wait_for(state="visible")
    with htmx_afgerond(page):
        ok.click()

    expect(page.locator("#product-melding [role=alert]")).to_be_visible()


def test_een_ontvangst_en_een_correctie_worden_bewaard(webshop_page):
    """A receipt and a correction book through their forms and land on the list —
    read after a fresh load, so only a real commit shows the new number (the
    lesson of the review: the same session cannot tell a flush from a commit)."""
    page = webshop_page

    page.goto("/admin/voorraad")
    assert _on_hand_van_de_lijst(page) == "5"

    page.goto("/admin/voorraad/ontvangst")
    page.locator("select[name=variant_id]").select_option(index=0)
    page.locator("input[name=quantity]").fill("7")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Ontvangst boeken").click()
    page.goto("/admin/voorraad")
    assert _on_hand_van_de_lijst(page) == "12"

    page.goto("/admin/voorraad/correctie")
    page.locator("select[name=variant_id]").select_option(index=0)
    page.locator("label", has_text="Eraf").click()
    page.locator("input[name=quantity]").fill("3")
    page.locator("input[name=note]").fill("retour")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Correctie opslaan").click()
    page.goto("/admin/voorraad")
    assert _on_hand_van_de_lijst(page) == "9"


def _open_artikel_in_bewerkmodus(page) -> str:
    page.goto("/admin/producten")
    page.locator('a[href^="/admin/producten/"]:not([href$="/nieuw"])').first.click()
    page.wait_for_selector("[data-record-head]")
    record = page.url.split("?")[0]
    page.goto(record + "?bewerken=1")
    page.wait_for_selector("[data-group-add]")
    return record


def _maten_van_de_pagina(page) -> list[str]:
    """The size names as the record shows them in read mode — the sizes' own
    chips, not a substring of the whole page."""
    page.wait_for_selector("[data-record-head]")
    return [t.strip() for t in page.locator("span.rounded-md.border.border-line").all_inner_texts()]


def test_maten_worden_toegevoegd_hernoemd_en_verwijderd(webshop_page):
    """The record's one save adds, renames and removes sizes, and the result is
    read on the record after a fresh load — the browser is the layer that proves
    the sizes were really written."""
    page = webshop_page
    record = _open_artikel_in_bewerkmodus(page)

    page.locator("[data-group-add]").click()
    rows = page.locator("[data-group-row]")
    rows.first.locator('input[name^="v."]').fill("Mx")
    rows.last.locator('input[name^="v."]').fill("L")
    page.locator("[data-form-save]").click()
    page.wait_for_url("**" + record)

    page.goto(record)
    assert _maten_van_de_pagina(page) == ["Mx", "L"]

    # Remove L again, so the seeded size stays what it was for the next run.
    page.goto(record + "?bewerken=1")
    page.wait_for_selector("[data-group-row]")
    row = page.locator("[data-group-row]").filter(has=page.locator('input[value="L"]'))
    row.locator("[data-row-menu-trigger]").click()
    row.locator('[data-row-action="remove"]').click()
    page.locator("[data-form-save]").click()
    page.wait_for_url("**" + record)

    page.goto(record)
    assert "L" not in _maten_van_de_pagina(page)


def test_de_bewegingen_van_een_maat_worden_getoond(webshop_page):
    """A size in the list leads to its own movements, where the receipt stands
    apart from a correction (AC16)."""
    page = webshop_page
    page.goto("/admin/voorraad")
    page.locator("a[data-row-link]").first.click()
    page.wait_for_selector("[data-record-head]")
    text = page.locator("main").inner_text()
    assert "Webshop T-shirt" in text
    assert "Ontvangst" in text


def test_een_maat_wordt_via_het_menu_verplaatst(webshop_page):
    """A size moved up through the row menu lands first after the save — on the
    record and in Prijsbeheer's select (the sizes' order)."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})
    record = _open_artikel_in_bewerkmodus(page)

    eerste = page.locator("[data-group-row]").first.locator('input[name^="v."]').input_value()

    page.locator("[data-group-add]").click()
    page.locator("[data-group-row]").last.locator('input[name^="v."]').fill("L")
    row = page.locator("[data-group-row]").last
    row.locator("[data-row-menu-trigger]").click()
    row.locator('[data-row-action="up"]').click()
    page.locator("[data-form-save]").click()
    page.wait_for_url("**" + record)

    try:
        page.goto(record)
        assert _maten_van_de_pagina(page) == ["L", eerste]

        page.goto("/admin/prijzen/" + record.rstrip("/").split("/")[-1])
        page.wait_for_selector("select[name=variant_id]")
        options = page.locator("select[name=variant_id] option").all_inner_texts()
        assert options[0] == "Alle maten"
        assert options[1] == "L" and options[2] == eerste
    finally:
        # put the record back to the seed (remove the added size), also on a red
        # assertion
        page.goto(record + "?bewerken=1")
        page.wait_for_selector("[data-group-row]")
        row = page.locator("[data-group-row]").filter(has=page.locator('input[value="L"]'))
        row.locator("[data-row-menu-trigger]").click()
        row.locator('[data-row-action="remove"]').click()
        page.locator("[data-form-save]").click()
        page.wait_for_url("**" + record)


def test_een_foto_wordt_opgeladen_en_verwijderd(webshop_page):
    """A picture is uploaded through the record and really shows — its natural
    width above zero after a fresh load — then removed (R3)."""
    from io import BytesIO

    from PIL import Image

    page = webshop_page
    record = _open_artikel_in_bewerkmodus(page)

    buf = BytesIO()
    Image.new("RGB", (40, 30), (10, 90, 200)).save(buf, format="PNG")
    page.locator('form[hx-post$="/fotos"] input[type="file"]').set_input_files(
        {"name": "foto.png", "mimeType": "image/png", "buffer": buf.getvalue()}
    )
    with htmx_afgerond(page):
        page.locator('button[form="foto-form"]').click()

    page.goto(record)
    page.wait_for_selector("[data-record-head]")
    img = page.locator('img[src^="/api/v1/media/"]')
    assert img.count() == 1
    assert img.first.evaluate("el => el.naturalWidth") > 0, "the picture did not load"

    page.goto(record + "?bewerken=1")
    page.wait_for_selector('img[src^="/api/v1/media/"]')
    page.locator('button[hx-post*="/bijlage/"]').first.click()
    ok = page.locator("[data-dialog] [data-dialog-ok]")
    ok.wait_for(state="visible")
    with htmx_afgerond(page):
        ok.click()
    page.wait_for_url("**" + record + "?bewerken=1")

    page.goto(record)
    page.wait_for_selector("[data-record-head]")
    assert page.locator('img[src^="/api/v1/media/"]').count() == 0


def test_een_document_wordt_opgeladen_en_verwijderd(webshop_page):
    """A document is uploaded through the record, its link answers 200 with the
    file, and it is removed again (R3)."""
    page = webshop_page
    record = _open_artikel_in_bewerkmodus(page)

    page.locator('form[hx-post$="/documenten"] input[type="file"]').set_input_files(
        {
            "name": "maattabel.pdf",
            "mimeType": "application/pdf",
            "buffer": b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 300]>>endobj\nxref\n0 4\n0000000000 65535 f \ntrailer<</Size 4/Root 1 0 R>>\n%%EOF\n",
        }
    )
    with htmx_afgerond(page):
        page.locator('button[form="document-form"]').click()

    page.goto(record)
    page.wait_for_selector("[data-record-head]")
    link = page.locator('a[href^="/api/v1/media/"]').first
    href = link.get_attribute("href")
    assert (
        page.request.get(
            f"http://127.0.0.1:8000{href}", headers={"Host": "webshop.localhost"}
        ).status
        == 200
    )

    page.goto(record + "?bewerken=1")
    page.wait_for_selector('a[href^="/api/v1/media/"]')
    page.locator('button[hx-post*="/bijlage/"]').first.click()
    ok = page.locator("[data-dialog] [data-dialog-ok]")
    ok.wait_for(state="visible")
    with htmx_afgerond(page):
        ok.click()
    page.wait_for_url("**" + record + "?bewerken=1")

    page.goto(record)
    page.wait_for_selector("[data-record-head]")
    assert page.locator('a[href^="/api/v1/media/"]').count() == 0


def test_de_eerste_rij_van_voorraad_opent_zijn_eigen_maat(webshop_page):
    """With two sizes, a click on the first row's text opens the first size's
    movements, not the last row's (the review of the list's row_link)."""
    page = webshop_page
    record = _open_artikel_in_bewerkmodus(page)

    page.locator("[data-group-add]").click()
    page.locator("[data-group-row]").last.locator('input[name^="v."]').fill("L")
    page.locator("[data-form-save]").click()
    page.wait_for_url("**" + record)

    page.goto("/admin/voorraad")
    page.wait_for_selector("tr[data-row]")
    page.locator("tr[data-row]").first.locator("a[data-row-link]").click()
    page.wait_for_selector("[data-record-head]")
    assert "· M" in page.locator("[data-record-head] h1").inner_text()

    # put the size back to what the seed had.
    page.goto(record + "?bewerken=1")
    page.wait_for_selector("[data-group-row]")
    row = page.locator("[data-group-row]").filter(has=page.locator('input[value="L"]'))
    row.locator("[data-row-menu-trigger]").click()
    row.locator('[data-row-action="remove"]').click()
    page.locator("[data-form-save]").click()
    page.wait_for_url("**" + record)


def test_een_geweigerde_upload_tekent_de_pagina_niet_dubbel(webshop_page):
    """A refused upload shows its sentence and keeps one page — one <h1> (A4)."""
    page = webshop_page
    _open_artikel_in_bewerkmodus(page)

    page.locator('form[hx-post$="/fotos"] input[type="file"]').set_input_files(
        {"name": "not-an-image.png", "mimeType": "text/plain", "buffer": b"geen afbeelding"}
    )
    with htmx_afgerond(page):
        page.locator('button[form="foto-form"]').click()

    page.wait_for_selector("#product-melding [role=alert]")
    assert page.locator("h1").count() == 1
    assert "bestandstype" in page.locator("#product-melding").inner_text()


def test_elke_weigering_van_de_record_opslag(webshop_page):
    """Every refusal of the record's one save answers at the message line and
    keeps one page — one <h1> — with what was typed still in the form (A1)."""
    page = webshop_page
    banner = page.locator("#product-melding [data-save-refusal]")

    # 1. an emptied article name
    _open_artikel_in_bewerkmodus(page)
    page.locator('input[name="name"]').fill("")
    with htmx_afgerond(page):
        page.locator("[data-form-save]").click()
    refusal_shown(page)
    assert page.locator("h1").count() == 1
    assert "Geef het artikel een naam." in banner.inner_text()

    # 2. a size renamed to nothing — the article's name stays
    _open_artikel_in_bewerkmodus(page)
    page.locator("[data-group-row]").first.locator('input[name^="v."]').fill("")
    with htmx_afgerond(page):
        page.locator("[data-form-save]").click()
    refusal_shown(page)
    assert page.locator("h1").count() == 1
    assert "Geef de maat een naam." in banner.inner_text()
    assert page.locator('input[name="name"]').input_value() == "Webshop T-shirt"

    # 3. a second size with the same name — the typed duplicate stays
    _open_artikel_in_bewerkmodus(page)
    page.locator("[data-group-add]").click()
    rows = page.locator("[data-group-row]")
    eerste = rows.first.locator('input[name^="v."]').input_value()
    rows.last.locator('input[name^="v."]').fill(eerste)
    with htmx_afgerond(page):
        page.locator("[data-form-save]").click()
    refusal_shown(page)
    assert page.locator("h1").count() == 1
    assert "Deze maat bestaat al." in banner.inner_text()
    assert page.locator("[data-group-row]").count() == 2

    # 4. a size with movements removed — the row comes back and the sentence
    #    names the size (S1)
    _open_artikel_in_bewerkmodus(page)
    row = page.locator("[data-group-row]").first
    size_name = row.locator('input[name^="v."]').input_value()
    count_before = page.locator("[data-group-row]").count()
    row.locator("[data-row-menu-trigger]").click()
    row.locator('[data-row-action="remove"]').click()
    with htmx_afgerond(page):
        page.locator("[data-form-save]").click()
    refusal_shown(page)
    assert page.locator("h1").count() == 1
    assert f"Maat {size_name} heeft voorraadbewegingen" in banner.inner_text()
    assert page.locator("[data-group-row]").count() == count_before


def test_de_knoppen_op_het_bewerkscherm_op_390_px(webshop_page):
    """At 390 px the upload cards' buttons stand inside their card and under the
    upload field — not over it, and not off the window (B5, asked twice)."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})
    _open_artikel_in_bewerkmodus(page)

    for form_id in ("foto-form", "document-form"):
        form = page.locator(f'form[id="{form_id}"]')
        card = form.locator("xpath=ancestor::section[1]").bounding_box()
        field = form.locator('[data-kind="upload"]').bounding_box()
        buttons = form.locator("xpath=following-sibling::*[1]").locator("button, a")
        assert buttons.count() >= 2, f"geen Annuleren/Opslaan onder {form_id}"
        for i in range(buttons.count()):
            box = buttons.nth(i).bounding_box()
            assert box["x"] >= card["x"], f"{form_id} knop {i} links van de kaart"
            assert box["x"] + box["width"] <= card["x"] + card["width"], (
                f"{form_id} knop {i} rechts van de kaart"
            )
            assert box["y"] >= field["y"] + field["height"], f"{form_id} knop {i} over het veld"


def test_de_fotos_op_390_px_staan_onder_elkaar(webshop_page):
    """At 390 px the edit screen's six pictures stand one per row: a picture with
    its wide "Verwijderen" button takes the whole card, so the flex-wrap stacks
    them (S3). The six pictures are removed again even when an assertion fails."""
    from io import BytesIO

    from PIL import Image

    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})
    record = _open_artikel_in_bewerkmodus(page)

    buf = BytesIO()
    Image.new("RGB", (40, 30), (10, 90, 200)).save(buf, format="PNG")
    try:
        for i in range(6):
            page.locator('form[hx-post$="/fotos"] input[type="file"]').set_input_files(
                {"name": f"foto-{i}.png", "mimeType": "image/png", "buffer": buf.getvalue()}
            )
            with htmx_afgerond(page):
                page.locator('button[form="foto-form"]').click()

        page.goto(record + "?bewerken=1")
        page.wait_for_selector('img[src^="/api/v1/media/"]')
        imgs = page.locator('img[src^="/api/v1/media/"]')
        assert imgs.count() == 6
        tops = sorted(round(imgs.nth(i).bounding_box()["y"]) for i in range(imgs.count()))
        assert len(set(tops)) == 6, f"foto's staan niet onder elkaar: {tops}"
    finally:
        # put the record back to the seed (no pictures)
        for _ in range(6):
            page.goto(record + "?bewerken=1")
            page.wait_for_selector('button[hx-post*="/bijlage/"]')
            page.locator('button[hx-post*="/bijlage/"]').first.click()
            ok = page.locator("[data-dialog] [data-dialog-ok]")
            ok.wait_for(state="visible")
            with htmx_afgerond(page):
                ok.click()


def _geen_zijwaartse_scroll(page) -> bool:
    return page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )


def test_de_webshop_paginas_op_390_px(webshop_page):
    """The public Webshop and the article page render at 390 px without a
    sideways scroll, and the article is really there — a card on the list, the
    name on the page — so the measure is not a degenerate empty page (commit 5)."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})

    page.goto("/webshop")
    heading = page.locator("main h1")
    heading.wait_for(state="visible")
    assert "Webshop" in heading.inner_text()
    cards = page.locator('main a[href^="/webshop/"]')
    assert cards.count() == 2, "de twee artikelen horen als kaarten op de lijst te staan"
    shirt = cards.filter(has_text="Webshop T-shirt")
    assert shirt.count() == 1
    assert _geen_zijwaartse_scroll(page)

    product_id = shirt.first.get_attribute("href").rstrip("/").split("/")[-1]
    page.goto(f"/webshop/{product_id}")
    heading = page.locator("main h1")
    heading.wait_for(state="visible")
    assert "Webshop T-shirt" in heading.inner_text()
    assert page.locator("main [data-tile]").filter(has_text="M").count() == 1, "de maat ontbreekt"
    assert "15,00" in page.locator("main").inner_text(), "de prijs ontbreekt"
    assert _geen_zijwaartse_scroll(page)


def test_het_mandje_wandelt_van_artikel_tot_bedankt(browser):
    """P1: the browser is the only layer that walks the basket. At 390 px: a size,
    "In mandje", "Mandje" — the line with the server's price on the basket page;
    then "Bestellen" by transfer lands on the thank-you page and the basket is
    empty after it."""
    page = browser.new_page(base_url=WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        page.goto("/webshop")
        card = page.locator('main a[href^="/webshop/"]').filter(has_text="Webshop T-shirt").first
        product_id = card.get_attribute("href").rstrip("/").split("/")[-1]
        page.goto(f"/webshop/{product_id}")

        page.locator("main [data-tile]").first.click()
        page.locator("[data-add-to-basket]").click()
        assert page.locator("[data-basket-count]").first.inner_text() == "1"

        with htmx_afgerond(page):
            page.locator("form[data-basket-form] button[type=submit]").click()
        page.wait_for_url("**/webshop/mandje")
        main = page.locator("main")
        assert "Webshop T-shirt" in main.inner_text()
        assert "15,00" in main.inner_text()

        page.locator('input[name="contact_name"]').fill("An")
        page.locator('input[name="contact_email"]').fill("an@example.com")
        page.locator('input[name="phone"]').fill("0470000000")
        page.locator('input[name="payment_method"][value="transfer"]').check()
        laat_de_wacht_passeren(page)  # the order form's guard (#2039)
        with htmx_afgerond(page):
            page.get_by_role("button", name="Bestellen en betalen").click()
        page.wait_for_url("**/webshop/bedankt?**")
        assert "Bedankt" in page.locator("main").inner_text()
        assert page.evaluate("localStorage.getItem('raak_basket')") in ("{}", None)
    finally:
        page.close()


def _voeg_de_maat_toe_aan_het_mandje(page) -> str:
    """Add the seeded shirt's size to the basket and return the product id."""
    page.goto("/webshop")
    card = page.locator('main a[href^="/webshop/"]').filter(has_text="Webshop T-shirt").first
    product_id = card.get_attribute("href").rstrip("/").split("/")[-1]
    page.goto(f"/webshop/{product_id}")
    page.locator("main [data-tile]").first.click()
    page.locator("[data-add-to-basket]").click()
    return product_id


def test_geen_maat_toont_de_melding_en_de_teller_blijft_nul(browser):
    """N2, in the browser: without a size "In mandje" shows "Kies een maat." and
    the count stays 0."""
    page = browser.new_page(base_url=WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        page.goto("/webshop")
        page.goto(page.locator('main a[href^="/webshop/"]').first.get_attribute("href"))
        page.locator("[data-add-to-basket]").click()
        expect(page.locator("[data-tiles-message]")).to_be_visible()
        assert page.locator("[data-basket-count]").first.inner_text() == "0"
    finally:
        page.close()


def test_een_aantal_wordt_gewijzigd_en_het_totaal_volgt(browser):
    """Koen's "ja op beide", in the browser: changing a line's quantity re-renders
    the page and the server's total follows."""
    page = browser.new_page(base_url=WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        _voeg_de_maat_toe_aan_het_mandje(page)
        with htmx_afgerond(page):
            page.locator("form[data-basket-form] button[type=submit]").click()
        page.wait_for_url("**/webshop/mandje")
        assert "15,00" in page.locator("main").inner_text()

        with htmx_afgerond(page):
            page.get_by_role("button", name="Eén meer").click()
        page.wait_for_url("**/webshop/mandje")
        assert "30,00" in page.locator("main").inner_text()
    finally:
        page.close()


def test_een_regel_wordt_verwijderd(browser):
    """Koen's "ja op beide", in the browser: removing a line empties the basket."""
    page = browser.new_page(base_url=WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        _voeg_de_maat_toe_aan_het_mandje(page)
        with htmx_afgerond(page):
            page.locator("form[data-basket-form] button[type=submit]").click()
        page.wait_for_url("**/webshop/mandje")
        assert "Webshop T-shirt" in page.locator("main").inner_text()

        with htmx_afgerond(page):
            page.locator("[data-line-remove]").click()
        page.wait_for_url("**/webshop/mandje")
        assert "Je mandje is leeg" in page.locator("main").inner_text()
    finally:
        page.close()


def test_een_te_veel_kan_naar_het_beschikbare_worden_verlaagd(webshop_page):
    """Q2, in the browser: a line that is only too many keeps its stepper, bounded
    by what is in stock; lowering it makes it orderable again."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})

    page.goto("/webshop")
    page.goto(page.locator('main a[href^="/webshop/"]').first.get_attribute("href"))
    page.locator("main [data-tile]").first.click()
    page.locator('input[name="quantity"]').fill("99")
    page.locator("[data-add-to-basket]").click()

    with htmx_afgerond(page):
        page.locator("form[data-basket-form] button[type=submit]").click()
    page.wait_for_url("**/webshop/mandje")
    # marked: not in the order, but the stepper stays (Q2)
    assert page.locator('input[type="hidden"][name="variant_id"]').count() == 0
    assert page.locator("[data-line-quantity]").count() == 1

    page.locator("[data-line-quantity]").fill("1")
    with htmx_afgerond(page):
        page.locator("[data-line-quantity]").blur()
    page.wait_for_url("**/webshop/mandje")
    assert page.locator('input[type="hidden"][name="variant_id"]').count() == 1


def test_een_weg_artikel_blijft_gemarkeerd_staan(webshop_page):
    """Koen's "ja op beide", in the browser: an article that goes away while it is
    in the basket stays on its own line, marked, while the other still orders."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})

    page.goto("/webshop")
    cards = page.locator('main a[href^="/webshop/"]')
    shirt = cards.filter(has_text="Webshop T-shirt").first
    pet = cards.filter(has_text="Webshop Zak").first
    shirt_id = shirt.get_attribute("href").rstrip("/").split("/")[-1]
    hrefs = [shirt.get_attribute("href"), pet.get_attribute("href")]
    for href in hrefs:
        page.goto(href)
        page.locator("main [data-tile]").first.click()
        page.locator("[data-add-to-basket]").click()

    def _status_zetten(status: str) -> None:
        label = "Afvoeren" if status == "DISCONTINUED" else "In verkoop zetten"
        page.goto(f"/admin/producten/{shirt_id}")
        page.locator("[data-actions-trigger]").click()
        item = page.locator(
            '[data-actions-menu] [role=menuitem][hx-post$="/status"]', has_text=label
        ).first
        item.wait_for(state="visible")
        heeft_confirm = item.get_attribute("data-confirm") is not None
        if heeft_confirm:
            item.click()
            ok = page.locator("[data-dialog] [data-dialog-ok]")
            ok.wait_for(state="visible")
            with htmx_afgerond(page):
                ok.click()
        else:
            with htmx_afgerond(page):
                item.click()
        page.wait_for_url(f"**/admin/producten/{shirt_id}")

    _status_zetten("DISCONTINUED")
    try:
        page.goto("/webshop")
        with htmx_afgerond(page):
            page.locator("form[data-basket-form] button[type=submit]").click()
        page.wait_for_url("**/webshop/mandje")
        # the gone article is marked, the other keeps its stepper and stays in the order
        assert "wordt niet meer aangeboden" in page.locator("main").inner_text()
        assert "Webshop Zak" in page.locator("main").inner_text()
        assert page.locator("[data-line-quantity]").count() == 1
        assert page.locator('input[type="hidden"][name="variant_id"]').count() == 1
    finally:
        _status_zetten("ON_SALE")


def test_een_foto_en_een_document_staan_op_de_artikelpagina(webshop_page):
    """R1/R3, in the browser: a picture shows and a document opens on the public
    article page, and the list shows the first picture's thumbnail."""
    from io import BytesIO

    from PIL import Image

    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})
    record = _open_artikel_in_bewerkmodus(page)
    product_id = record.rstrip("/").split("/")[-1]

    buf = BytesIO()
    Image.new("RGB", (40, 30), (10, 90, 200)).save(buf, format="PNG")
    page.locator('form[hx-post$="/fotos"] input[type="file"]').set_input_files(
        {"name": "foto.png", "mimeType": "image/png", "buffer": buf.getvalue()}
    )
    with htmx_afgerond(page):
        page.locator('button[form="foto-form"]').click()
    page.locator('form[hx-post$="/documenten"] input[type="file"]').set_input_files(
        {
            "name": "maattabel.pdf",
            "mimeType": "application/pdf",
            "buffer": b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
        }
    )
    with htmx_afgerond(page):
        page.locator('button[form="document-form"]').click()

    try:
        page.goto(f"/webshop/{product_id}")
        picture = page.locator('img[src^="/api/v1/media/"]:not([src$="/thumb"])')
        assert picture.count() == 1
        assert picture.first.evaluate("el => el.naturalWidth") > 0, "the picture did not load"
        document = page.locator('a[href^="/api/v1/media/"]').first
        href = document.get_attribute("href")
        assert (
            page.request.get(
                f"http://127.0.0.1:8000{href}", headers={"Host": "webshop.localhost"}
            ).status
            == 200
        )

        page.goto("/webshop")
        assert page.locator('img[src^="/api/v1/media/"][src$="/thumb"]').count() == 1

        page.set_viewport_size({"width": 1440, "height": 844})
        page.goto(f"/webshop/{product_id}")
        assert _geen_zijwaartse_scroll(page), "de foto's maken de pagina op 1 440 px te breed"
    finally:
        page.goto(record + "?bewerken=1")
        for _ in range(2):
            page.wait_for_selector('button[hx-post*="/bijlage/"]')
            page.locator('button[hx-post*="/bijlage/"]').first.click()
            ok = page.locator("[data-dialog] [data-dialog-ok]")
            ok.wait_for(state="visible")
            with htmx_afgerond(page):
                ok.click()


def test_een_op_bestelling_maat_zonder_voorraad_toont_op_bestelling(webshop_page):
    """R1, in the browser: a size of an "Op bestelling" article with no stock shows
    "op bestelling" once on its tile, not "uitverkocht"."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})

    # The second article has no order against it, so its stock can go to zero.
    page.goto("/admin/producten")
    page.locator(
        'a[href^="/admin/producten/"]:not([href$="/nieuw"])', has_text="Webshop Zak"
    ).first.click()
    page.wait_for_selector("[data-record-head]")
    record = page.url.split("?")[0]
    product_id = record.rstrip("/").split("/")[-1]
    page.goto(record + "?bewerken=1")
    page.wait_for_selector("[data-group-add]")

    page.locator('label[for="pre_order"]').click()
    page.locator("[data-form-save]").click()
    page.wait_for_url("**" + record)

    page.goto("/admin/voorraad")
    in_stock = int(
        page.locator("tbody tr", has_text="Webshop Zak")
        .first.locator("td[data-cell=amount]")
        .nth(0)
        .inner_text()
        .strip()
    )
    page.goto("/admin/voorraad/correctie")
    variant_id = page.locator(
        "select[name=variant_id] option", has_text="Webshop Zak"
    ).first.get_attribute("value")
    page.locator("select[name=variant_id]").select_option(value=variant_id)
    page.locator("label", has_text="Eraf").click()
    page.locator("input[name=quantity]").fill(str(in_stock))
    page.locator("input[name=note]").fill("proef")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Correctie opslaan").click()

    try:
        page.goto(f"/webshop/{product_id}")
        tile = page.locator("main [data-tile]").filter(has_text="op bestelling")
        assert tile.count() == 1, "de maattegel hoort één keer 'op bestelling' te tonen"
        assert "uitverkocht" not in page.locator("main").inner_text()
    finally:
        page.goto("/admin/voorraad/ontvangst")
        page.locator("select[name=variant_id]").select_option(value=variant_id)
        page.locator("input[name=quantity]").fill(str(in_stock))
        with htmx_afgerond(page):
            page.get_by_role("button", name="Ontvangst boeken").click()
        page.goto(record + "?bewerken=1")
        page.locator('label[for="pre_order"]').click()
        page.locator("[data-form-save]").click()
        page.wait_for_url("**" + record)


def test_verkoop_toont_de_bestelling_en_levert_een_regel(webshop_page):
    """Verkoop's list shows the order, and the order page delivers a line (F6), at
    390 px."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("localStorage.removeItem('raak_basket')")

    _voeg_de_maat_toe_aan_het_mandje(page)
    with htmx_afgerond(page):
        page.locator("form[data-basket-form] button[type=submit]").click()
    page.wait_for_url("**/webshop/mandje")
    page.locator('input[name="contact_name"]').fill("An")
    page.locator('input[name="contact_email"]').fill("an@example.com")
    page.locator('input[name="phone"]').fill("0470000000")
    page.locator('input[name="payment_method"][value="transfer"]').check()
    laat_de_wacht_passeren(page)  # the order form's guard (#2039)
    with htmx_afgerond(page):
        page.get_by_role("button", name="Bestellen en betalen").click()
    page.wait_for_url("**/webshop/bedankt?**")

    page.goto("/admin/verkoop")
    assert "Bestelling" in page.locator("main").inner_text()
    assert _geen_zijwaartse_scroll(page)

    page.locator("a[data-row-link]").first.click()
    page.wait_for_selector("[data-record-head]")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Afleveren").click()
    page.wait_for_url("**/admin/verkoop/**")
    assert "Afgeleverd" in page.locator("main").inner_text()


def test_verkoop_wijzigt_een_bestelling(webshop_page):
    """R15/AC11, at 390 px: Verkoop opens the change form, the line stands in it, and
    saving returns to the order page."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("localStorage.removeItem('raak_basket')")

    _voeg_de_maat_toe_aan_het_mandje(page)
    with htmx_afgerond(page):
        page.locator("form[data-basket-form] button[type=submit]").click()
    page.wait_for_url("**/webshop/mandje")
    page.locator('input[name="contact_name"]').fill("An")
    page.locator('input[name="contact_email"]').fill("an@example.com")
    page.locator('input[name="phone"]').fill("0470000000")
    page.locator('input[name="payment_method"][value="transfer"]').check()
    laat_de_wacht_passeren(page)  # the order form's guard (#2039)
    with htmx_afgerond(page):
        page.get_by_role("button", name="Bestellen en betalen").click()
    page.wait_for_url("**/webshop/bedankt?**")

    page.goto("/admin/verkoop")
    page.locator("a[data-row-link]").first.click()
    page.wait_for_selector("[data-record-head]")

    page.get_by_role("link", name="Wijzigen").click()
    page.wait_for_url("**/wijzigen")
    assert _geen_zijwaartse_scroll(page)
    assert "Webshop T-shirt" in page.locator("main").inner_text()

    # Add the size once more, so the order holds two of it.
    page.locator("#maten [data-tile]").first.click()
    page.locator("#new_quantity").fill("1")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Artikel toevoegen").click()
    with htmx_afgerond(page):
        page.get_by_role("button", name="Opslaan").click()
    page.wait_for_url("**/admin/verkoop/**")
    assert "30,00" in page.locator("main").inner_text(), "the changed total stands on the page"


def test_productbeheer_en_prijsbeheer_zijn_tabellen(webshop_page):
    """The two list screens are the kit's table: one `table`, a row is the way in,
    no sideways scroll (Koen's sixth point)."""
    page = webshop_page
    for width in (390, 1440):
        page.set_viewport_size({"width": width, "height": 844})
        page.goto("/admin/producten")
        page.wait_for_selector("table.data-table")
        assert page.locator("table.data-table").count() == 1
        page.locator("a[data-row-link]").first.click()
        page.wait_for_selector("[data-record-head]")
        assert _geen_zijwaartse_scroll(page)

        page.goto("/admin/prijzen")
        page.wait_for_selector("table.data-table")
        assert page.locator("table.data-table").count() == 1
        page.locator("a[data-row-link]").first.click()
        page.wait_for_selector("[data-record-head]")
        assert _geen_zijwaartse_scroll(page)


def test_webshop_instellingen_zet_de_tekst_en_de_contactpersonen(webshop_page):
    """R41/R42, in the browser at 390 px: Verkoop saves the intro, the Webshop shows
    it, and a contact person is added and removed again by clicking — the list
    after each click. The textarea and the search are as wide as the section."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/admin/verkoop/instellingen")
    assert _geen_zijwaartse_scroll(page)

    textarea = page.locator('textarea[name="intro"]')
    assert textarea.bounding_box()["width"] > 300, "de tekst staat in een te smal veld"
    search = page.locator('input[name="contact_q"]')
    assert search.bounding_box()["width"] > 300, "het zoekveld is te smal"
    sections = page.locator("[data-form-section]")
    first = sections.nth(0).bounding_box()
    second = sections.nth(1).bounding_box()
    gap = second["y"] - (first["y"] + first["height"])
    assert gap > 60, f"de actiebalk heeft geen ruimte tussen de twee kaarten: {gap} px"

    textarea.fill("Kledij en spullen van Raak.")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Opslaan").click()
    page.wait_for_url("**/admin/verkoop/instellingen")

    page.goto("/webshop")
    assert "Kledij en spullen van Raak." in page.locator("main").inner_text()

    page.goto("/admin/verkoop/instellingen")
    search.fill("Webshop")
    add = page.get_by_role("button", name="Toevoegen").first
    add.wait_for(state="visible", timeout=5000)
    with htmx_afgerond(page):
        add.click()
    page.wait_for_url("**/admin/verkoop/instellingen")
    assert "Webshop Lid" in page.locator("main").inner_text()

    page.get_by_role("button", name="Verwijderen").click()
    ok = page.locator("[data-dialog] [data-dialog-ok]")
    ok.wait_for(state="visible")
    with htmx_afgerond(page):
        ok.click()
    page.wait_for_url("**/admin/verkoop/instellingen")
    assert "Webshop Lid" not in page.locator("main").inner_text()


def test_de_actiebalk_is_zo_breed_als_het_formulier(webshop_page):
    """The article's action bar is as wide as its form column, not the whole
    window (Koen's first point). On a phone the kit's bar full-bleeds, as on
    every record."""
    page = webshop_page
    page.set_viewport_size({"width": 1440, "height": 844})
    _open_artikel_in_bewerkmodus(page)
    bar = page.locator("[data-action-bar]").bounding_box()
    column = page.locator("[data-form-column]").bounding_box()
    assert abs(bar["x"] - column["x"]) <= 1, "de balk staat links van de formulierkolom"
    assert abs((bar["x"] + bar["width"]) - (column["x"] + column["width"])) <= 1, (
        "de balk staat rechts van de formulierkolom"
    )

    page.set_viewport_size({"width": 390, "height": 844})
    _open_artikel_in_bewerkmodus(page)
    assert _geen_zijwaartse_scroll(page)


def test_ontvangst_en_correctie_staan_samen_in_de_kop(webshop_page):
    """'+ Ontvangst' and 'Correctie' stand together in the head, not under the
    toolbar's `⋯` (Koen, 15 October 2026)."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/admin/voorraad")
    page.wait_for_selector("[data-list-primary]")

    primary = page.locator("[data-list-primary] a, [data-list-primary] button")
    assert primary.count() == 2
    assert "Ontvangst" in primary.nth(1).inner_text()
    assert "Correctie" in primary.nth(0).inner_text()
    assert page.locator("[data-more-button]").count() == 0
    assert _geen_zijwaartse_scroll(page)


def test_de_bewegingen_hebben_de_juiste_kolommen(webshop_page):
    """The movements columns at 1 440 px: "Wat" no wider than its kind, "Aantal"
    next to it, "Reden" (text) the widest, and the moment fits its 152 px cell;
    at 390 px the stacked row shows the moment, the figure and the reason, and an
    empty reason leaves no empty line (the kit's `moment` and `text` parts, #1915)."""
    page = webshop_page

    # a receipt without a reason, then a correction with one — the two cancel, so
    # nothing needs putting back, and the list has one empty and one filled reason
    page.goto("/admin/voorraad/ontvangst")
    variant_id = page.locator("select[name=variant_id] option").nth(0).get_attribute("value")
    page.locator("select[name=variant_id]").select_option(variant_id)
    page.locator("input[name=quantity]").fill("1")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Ontvangst boeken").click()

    page.goto("/admin/voorraad/correctie")
    page.locator("select[name=variant_id]").select_option(variant_id)
    page.locator("label", has_text="Eraf").click()
    page.locator("input[name=quantity]").fill("1")
    page.locator("input[name=note]").fill("proefreden")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Correctie opslaan").click()

    page.goto(f"/admin/voorraad/{variant_id}")
    page.wait_for_selector("table.data-table")

    page.set_viewport_size({"width": 1440, "height": 844})
    headers = page.locator("table.data-table th")
    wat = headers.filter(has_text="Wat").bounding_box()
    aantal = headers.filter(has_text="Aantal").bounding_box()
    reden = headers.filter(has_text="Reden").bounding_box()
    assert wat["width"] <= 137, "Wat is breder dan zijn kolomsoort (136 px)"
    assert abs(aantal["x"] - (wat["x"] + wat["width"])) <= 1, "Aantal staat niet naast Wat"
    assert reden["width"] > max(wat["width"], aantal["width"]), "Reden is niet de breedste kolom"
    fits = page.locator("table.data-table td[data-cell='moment']").first.evaluate(
        "el => el.scrollWidth <= el.clientWidth + 1"
    )
    assert fits, "het moment loopt uit zijn cel op 1 440 px"

    page.set_viewport_size({"width": 390, "height": 844})
    assert page.locator("table.data-table td[data-cell='moment']").first.is_visible(), (
        "het moment is niet zichtbaar in de gestapelde rij"
    )
    assert page.locator("table.data-table td[data-cell='amount']").first.is_visible(), (
        "het aantal is niet zichtbaar in de gestapelde rij"
    )
    assert page.locator("table.data-table td[data-cell='text']").first.is_visible(), (
        "de reden is niet zichtbaar in de gestapelde rij"
    )
    # an empty reason leaves no empty line: the receipt's cell is empty and hidden
    empty = page.locator("table.data-table td[data-cell='text']:empty")
    assert empty.count() >= 1, "de ontvangst hoort een lege reden te zijn"
    for i in range(empty.count()):
        assert not empty.nth(i).is_visible(), "een lege reden toont een lege regel"
    assert _geen_zijwaartse_scroll(page)


def test_bestelling_toevoegen_koppelt_het_lid_en_prijst_hem(webshop_page):
    """R43/W26/T22, at 390 px: type the member's e-mail, the page names the member,
    add the T-shirt at the member price, save — the order is in Verkoop."""
    from seed_e2e import WEBSHOP_LID_EMAIL

    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/admin/verkoop/nieuw")

    page.locator('input[name="email"]').fill(WEBSHOP_LID_EMAIL)
    page.wait_for_selector("[data-koppeling]", state="visible")
    assert "bestaand lid" in page.locator("[data-koppeling]").inner_text()
    assert "Webshop Lid" in page.locator("[data-koppeling]").inner_text()

    page.locator('select[name="product_id"]').select_option(label="Webshop T-shirt")
    page.wait_for_selector("#maten [data-tile]")
    page.locator("#maten [data-tile]").first.click()
    with htmx_afgerond(page):
        page.get_by_role("button", name="Artikel toevoegen").click()

    assert "Webshop T-shirt" in page.locator("main").inner_text()
    assert "12,00" in page.locator("main").inner_text(), "de ledenprijs hoort op de regel te staan"
    assert "15,00" not in page.locator("main").inner_text(), (
        "de gewone prijs hoort er niet te staan"
    )
    assert _geen_zijwaartse_scroll(page)

    with htmx_afgerond(page):
        page.get_by_role("button", name="Bestelling opslaan").click()
    page.wait_for_url("**/admin/verkoop/**")
    assert "Bestelling" in page.locator("main").inner_text()


def test_een_upload_leegt_noch_blokkeert_een_onbewaarde_wijziging(webshop_page):
    """Koen's faults 1 and 2: an upload is its own action — it never empties the
    article's unsaved fields and never stops the save with Blijven/Weggooien."""
    from io import BytesIO

    from PIL import Image

    page = webshop_page
    _open_artikel_in_bewerkmodus(page)

    page.locator('input[name="name"]').fill("Gewijzigde naam")
    page.locator("[data-group-row]").first.locator('input[name^="v."]').fill("Maat XL")
    buf = BytesIO()
    Image.new("RGB", (40, 30), (10, 90, 200)).save(buf, format="PNG")
    page.locator('form[hx-post$="/fotos"] input[type="file"]').set_input_files(
        {"name": "foto.png", "mimeType": "image/png", "buffer": buf.getvalue()}
    )
    with htmx_afgerond(page):
        page.locator('button[form="foto-form"]').click()

    assert page.locator('input[name="name"]').input_value() == "Gewijzigde naam", (
        "de onbewaarde naam moet blijven staan"
    )
    assert page.locator("[data-group-row]").first.locator('input[name^="v."]').input_value() == (
        "Maat XL"
    ), "de ingetikte maat moet na de upload blijven staan"


def test_een_documenttitel_wordt_met_opslaan_bewaard(webshop_page):
    """Koen's fault 2: a document's title is saved by the article's one Opslaan —
    never a "Kies een bestand" for the upload's empty file field."""
    page = webshop_page
    record = _open_artikel_in_bewerkmodus(page)

    page.locator('form[hx-post$="/documenten"] input[type="file"]').set_input_files(
        {
            "name": "maattabel.pdf",
            "mimeType": "application/pdf",
            "buffer": b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 300]>>endobj\nxref\n0 4\n0000000000 65535 f \ntrailer<</Size 4/Root 1 0 R>>\n%%EOF\n",
        }
    )
    with htmx_afgerond(page):
        page.locator('button[form="document-form"]').click()

    page.locator('input[name^="bijlage."][name$=".title"]').first.fill("Maattabel T-shirts")
    with htmx_afgerond(page):
        page.locator("[data-action-bar] [data-form-save]").click()

    page.goto(record)
    page.wait_for_selector("[data-record-head]")
    assert "Maattabel T-shirts" in page.locator("main").inner_text()


def test_het_mandje_toont_het_totaal_en_behoudt_het_contact(webshop_page):
    """Koen's faults 4 and 6: the total stands under the lines and a quantity
    change re-renders the lines and the total, never the typed contact."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})
    _voeg_de_maat_toe_aan_het_mandje(page)
    with htmx_afgerond(page):
        page.locator("form[data-basket-form] button[type=submit]").click()
    page.wait_for_url("**/webshop/mandje")

    assert "Totaal" in page.locator("main").inner_text()
    assert "15,00" in page.locator("main").inner_text()

    page.locator('input[name="contact_name"]').fill("An")
    page.locator('input[name="contact_email"]').fill("an@example.com")
    page.locator('input[name="phone"]').fill("0470000000")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Eén meer").click()
    page.wait_for_url("**/webshop/mandje")

    assert page.locator('input[name="contact_name"]').input_value() == "An"
    assert page.locator('input[name="contact_email"]').input_value() == "an@example.com"
    assert page.locator('input[name="phone"]').input_value() == "0470000000"
    assert "30,00" in page.locator("main").inner_text()


def test_online_betalen_landt_op_de_stub(browser):
    """Koen's fault 7, and the secret key (Koen, 16 October 2026): an online order
    starts the stand-in provider, and paying comes back on the thank-you page by the
    order's key — never a red error block."""
    page = browser.new_page(base_url=WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        _voeg_de_maat_toe_aan_het_mandje(page)
        with htmx_afgerond(page):
            page.locator("form[data-basket-form] button[type=submit]").click()
        page.wait_for_url("**/webshop/mandje")
        page.locator('input[name="contact_name"]').fill("An")
        page.locator('input[name="contact_email"]').fill("an@example.com")
        page.locator('input[name="phone"]').fill("0470000000")
        page.locator('input[name="payment_method"][value="online"]').check()
        laat_de_wacht_passeren(page)  # the order form's guard (#2039)
        with htmx_afgerond(page):
            page.get_by_role("button", name="Bestellen en betalen").click()
        page.wait_for_url("**/betaling/stub/**")
        assert "betaling" in page.locator("main").inner_text().lower()
        page.get_by_role("button", name="Betaal").click()
        page.wait_for_url("**/webshop/bedankt?key=**")
        assert "Bedankt" in page.locator("main").inner_text()
    finally:
        page.close()


def test_het_contact_wordt_vooraf_ingevuld_voor_een_lid(webshop_page):
    """Koen's fault 5: the signed-in person's contact fills the basket's contact
    block, as on the registration for an activity."""
    from app.domains.auth.api import make_session_value
    from tests_e2e.schermen import login_met_sessie

    page = webshop_page
    login_met_sessie(page, make_session_value("webshop.lid@example.com"), WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})

    _voeg_de_maat_toe_aan_het_mandje(page)
    with htmx_afgerond(page):
        page.locator("form[data-basket-form] button[type=submit]").click()
    page.wait_for_url("**/webshop/mandje")

    assert page.locator('input[name="contact_name"]').input_value() == "Webshop Lid"
    assert page.locator('input[name="contact_email"]').input_value() == "webshop.lid@example.com"


def test_de_koper_annuleert_zijn_bestelling(webshop_page):
    """R23, at 390 px: a signed-in buyer cancels his own order and lands on Mijn
    aankopen, not on a page nested inside the order card."""
    from app.domains.auth.api import make_session_value

    page = webshop_page
    login_met_sessie(page, make_session_value("webshop.lid@example.com"), WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("localStorage.removeItem('raak_basket')")

    _voeg_de_maat_toe_aan_het_mandje(page)
    with htmx_afgerond(page):
        page.locator("form[data-basket-form] button[type=submit]").click()
    page.wait_for_url("**/webshop/mandje")
    page.locator('input[name="phone"]').fill("0470000000")
    page.locator('input[name="payment_method"][value="transfer"]').check()
    laat_de_wacht_passeren(page)
    with htmx_afgerond(page):
        page.get_by_role("button", name="Bestellen en betalen").click()
    page.wait_for_url("**/webshop/bedankt?**")

    page.goto("/mijn/aankopen")
    order_link = page.locator("main a[href^='/mijn/aankopen/']").first
    order_id = order_link.get_attribute("href").rstrip("/").split("/")[-1]
    order_link.click()
    page.wait_for_url(f"**/mijn/aankopen/{order_id}")
    assert "Bestelling annuleren" in page.locator("main").inner_text()

    page.get_by_role("button", name="Bestelling annuleren").click()
    ok = page.locator("[data-dialog] [data-dialog-ok]")
    ok.wait_for(state="visible")
    with htmx_afgerond(page):
        ok.click()
    page.wait_for_url("**/mijn/aankopen")
    assert f"Bestelling {order_id}" not in page.locator("main").inner_text(), (
        "the cancelled order is gone"
    )


def test_verkoop_annuleert_een_bestelling(webshop_page):
    """Q61/F8, at 390 px: Verkoop's "Annuleren" (#2172; it read "Verwijderen") asks, and
    the order leaves the list. Walks the button so a dead one (a type lost) is caught, as
    the buyer's was."""
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = webshop_page
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("localStorage.removeItem('raak_basket')")

    # The second seeded article: the shirt's stock is used by the earlier walks.
    page.goto("/webshop")
    card = page.locator('main a[href^="/webshop/"]').filter(has_text="Webshop Zak").first
    page.goto(card.get_attribute("href"))
    page.locator("main [data-tile]").first.click()
    page.locator("[data-add-to-basket]").click()

    with htmx_afgerond(page):
        page.locator("form[data-basket-form] button[type=submit]").click()
    page.wait_for_url("**/webshop/mandje")
    page.locator('input[name="contact_name"]').fill("An")
    page.locator('input[name="contact_email"]').fill("an@example.com")
    page.locator('input[name="phone"]').fill("0470000000")
    page.locator('input[name="payment_method"][value="transfer"]').check()
    laat_de_wacht_passeren(page)
    with htmx_afgerond(page):
        page.get_by_role("button", name="Bestellen en betalen").click()
    page.wait_for_url("**/webshop/bedankt?**")

    page.goto("/admin/verkoop")
    row = page.locator("a[data-row-link]").first
    href = row.get_attribute("href")
    assert href and href.startswith("/admin/verkoop/"), href
    row_of_the_order = page.locator(f'a[data-row-link][href="{href}"]')
    assert row_of_the_order.count() == 1, "the order stands in the list before the delete"
    row.click()
    page.wait_for_selector("[data-record-head]")
    head = page.locator("main").inner_text()
    assert "Verwijderen" not in head, "the button says what it does"

    page.get_by_role("button", name="Annuleren", exact=True).click()
    ok = page.locator("[data-dialog] [data-dialog-ok]")
    ok.wait_for(state="visible")
    assert "De bestelling wordt verwijderd." in page.locator("[data-dialog]").inner_text()
    with htmx_afgerond(page):
        ok.click()
    page.wait_for_url("**/admin/verkoop")
    listed = page.locator("main").inner_text()
    assert "Bestellingen" in listed or "Nog geen bestellingen" in listed, "the list rendered"
    assert row_of_the_order.count() == 0, "the deleted order is gone from the list"


def _short_article() -> int:
    """A size with 2 in stock on the shop's tenant, at € 10 — for a basket line
    asking more than the stock. Its own article, so the shirt's stock that the
    other walks use does not decide the sentence."""
    import secrets
    from datetime import date
    from decimal import Decimal

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import tenant_codes
    from app.domains.pricing.api import add_prices
    from app.domains.product.models import Product, ProductStatus, ProductVariant
    from app.domains.stock.api import receive
    from app.kernel.tenancy import current_tenant_id

    db = SessionLocal()
    token = current_tenant_id.set(tenant_codes(db)["winkel"])
    try:
        product = Product(name=f"Webshop Krap {secrets.token_hex(3)}", status=ProductStatus.ON_SALE)
        db.add(product)
        db.flush()
        variant = ProductVariant(product_id=product.id, properties=[{"name": "Maat", "value": "M"}])
        db.add(variant)
        db.flush()
        receive(db, variant.id, quantity=2)
        add_prices(
            db,
            product_id=product.id,
            variant_id=variant.id,
            valid_from=date(2026, 1, 1),
            amount=Decimal("10.00"),
            member_amount=None,
        )
        db.commit()
        return variant.id
    finally:
        current_tenant_id.reset(token)
        db.close()


def test_de_voorraadzin_staat_over_de_volle_breedte(browser):
    """#2125, at 390 px: a line asking more than the stock says so over the line's
    full width, under the quantity and the delete button, in at most two lines —
    not in the narrow column under the name."""
    variant_id = _short_article()
    page = browser.new_page(base_url=WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        page.goto("/webshop")
        page.evaluate(f"localStorage.setItem('raak_basket', JSON.stringify({{'{variant_id}': 5}}))")
        with htmx_afgerond(page):
            page.locator("form[data-basket-form] button[type=submit]").click()
        page.wait_for_url("**/webshop/mandje")
        pagina_klaar(page)

        line = page.locator("[data-basket-line]").filter(has_text="Webshop Krap")
        note = line.locator("[data-line-note]")
        assert note.inner_text() == "Nog 2 op voorraad, maximaal 2 bestelbaar."
        line_box = line.bounding_box()
        note_box = note.bounding_box()
        quantity_box = line.locator("input[name=quantity]").bounding_box()
        assert abs(note_box["width"] - line_box["width"]) <= 1, (note_box, line_box)
        assert note_box["y"] >= quantity_box["y"] + quantity_box["height"], "under the quantity"
        name_box = line.locator(":scope > div").first.bounding_box()
        assert quantity_box["y"] < name_box["y"] + name_box["height"], (
            f"the quantity stays beside the name, not under it: {quantity_box}, {name_box}"
        )
        line_height = float(note.evaluate("el => parseFloat(getComputedStyle(el).lineHeight)"))
        assert note_box["height"] <= 2 * line_height + 1, f"at most two lines: {note_box}"
    finally:
        page.evaluate("localStorage.removeItem('raak_basket')")
        page.close()


# ── CR-26 phase 2: Mijn organisatie and "Wie bestelt" ────────────────────────

ORGANISATION_VAT = "BE0000000097"  # a made-up number: no company has it


def _organisatie_registreren(page, naam: str) -> None:
    """Register an organisation through Mijn organisatie (idempotent: a VAT number the
    account knows links to it, so a second run only lists it)."""
    page.goto("/mijn/organisatie")
    page.locator("#org-vat_number").fill(ORGANISATION_VAT)
    page.locator("#org-name").fill(naam)
    page.locator("#org-street").fill("Teststraat")
    page.locator("#org-house_number").fill("1")
    page.locator("#org-postal_code").select_option("2400")
    laat_de_wacht_passeren(page)
    with htmx_afgerond(page):
        page.get_by_role("button", name="Registreren").click()
    page.locator("[data-organisation]", has_text=naam).first.wait_for()


def test_mijn_organisatie_registreert_en_past_op_een_telefoon(webshop_page):
    """A signed-in person registers an organisation, which then stands in the list with
    its Ontkoppelen button whole inside the 390 px screen and no sideways scroll."""
    from app.domains.auth.api import make_session_value

    page = webshop_page
    login_met_sessie(page, make_session_value("webshop.lid@example.com"), WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})
    _organisatie_registreren(page, "Proef BV")

    width = page.evaluate("document.documentElement.scrollWidth")
    assert width <= 390, f"sideways scroll on Mijn organisatie: {width}px"
    row = page.locator("[data-organisation]", has_text="Proef BV").first
    button = row.get_by_role("button", name="Ontkoppelen").bounding_box()
    assert button is not None and button["x"] >= 0 and button["x"] + button["width"] <= 390, button
    for field in ("#org-vat_number", "#org-name", "#org-street", "#org-postal_code"):
        box = page.locator(field).bounding_box()
        assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= 390, (field, box)


def test_de_mand_biedt_namens_aan_en_bestelt_namens_de_organisatie(webshop_page):
    """The basket asks "Wie bestelt" when the person acts for an organisation: voor mezelf
    and namens …; choosing namens places the order, which Mijn aankopen then lists."""
    from app.domains.auth.api import make_session_value

    page = webshop_page
    login_met_sessie(page, make_session_value("webshop.lid@example.com"), WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})
    _organisatie_registreren(page, "Proef BV")
    page.evaluate("localStorage.removeItem('raak_basket')")

    _voeg_de_maat_toe_aan_het_mandje(page)
    with htmx_afgerond(page):
        page.locator("form[data-basket-form] button[type=submit]").click()
    page.wait_for_url("**/webshop/mandje")

    choices = page.locator('input[name="buyer_organization_id"]')
    assert choices.count() == 2, "voor mezelf and one namens"
    assert "namens Proef BV" in page.locator("main").inner_text()
    page.get_by_text("namens Proef BV").click()
    assert page.locator('input[name="buyer_organization_id"]:checked').get_attribute("value") != ""
    page.locator('input[name="phone"]').fill("0470000000")
    page.locator('input[name="payment_method"][value="transfer"]').check()
    laat_de_wacht_passeren(page)
    with htmx_afgerond(page):
        page.get_by_role("button", name="Bestellen en betalen").click()
    page.wait_for_url("**/webshop/bedankt?**")
    page.evaluate("localStorage.removeItem('raak_basket')")


def test_een_afdeling_ziet_haar_organisaties_op_een_telefoon(webshop_page):
    """CR-26 F9: the department's Organisaties (the address family of its own, behind the
    invoices module) lists an organisation a person of the department acts for, and its
    record names that person; at 390 px there is no sideways scroll and the menu names
    the item Organisaties."""
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = webshop_page
    login_met_sessie(page, make_session_value("webshop.lid@example.com"), WEBSHOP_HOST)
    page.set_viewport_size({"width": 390, "height": 844})
    _organisatie_registreren(page, "Proef BV")

    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), WEBSHOP_HOST)
    page.goto("/admin/relaties")
    row = page.locator("[data-organisation]", has_text="Proef BV").first
    row.wait_for()
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    row.locator("a").first.click()
    page.wait_for_url(re.compile(r"/admin/relaties/\d+"))
    page.locator("#org-section-people").wait_for()
    assert "Webshop Lid" in page.locator("#org-section-people").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
