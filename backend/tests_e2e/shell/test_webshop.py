"""E2E CR-21 (#1887) — the shop's back-office, on a tenant of its own.

The shop is off by default for every kind of tenant, and a tenant's module set is
cached in the server process, so the browser tests run on a seeded tenant of its
own (`webshop` in `seed_e2e.py`), reached by hostname (`TENANT_HOSTNAMES` in
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
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import htmx_afgerond, login_met_sessie  # noqa: E402

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
    banner.wait_for(state="visible")
    assert page.locator("h1").count() == 1
    assert "Geef het artikel een naam." in banner.inner_text()

    # 2. a size renamed to nothing — the article's name stays
    _open_artikel_in_bewerkmodus(page)
    page.locator("[data-group-row]").first.locator('input[name^="v."]').fill("")
    with htmx_afgerond(page):
        page.locator("[data-form-save]").click()
    banner.wait_for(state="visible")
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
    banner.wait_for(state="visible")
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
    banner.wait_for(state="visible")
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


def test_ontvangst_in_de_kop_en_correctie_onder_het_menu(webshop_page):
    """'+ Ontvangst' alone in the head, 'Correctie' under the toolbar's `⋯` — the
    list norm (Koen's fourth point, corrected by the read)."""
    page = webshop_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/admin/voorraad")
    page.wait_for_selector("[data-list-primary]")

    primary = page.locator("[data-list-primary] a, [data-list-primary] button")
    assert primary.count() == 1
    assert "Ontvangst" in primary.first.inner_text()

    page.locator("[data-more-button]").click()
    menu = page.locator("[data-more-menu]")
    menu.wait_for(state="visible")
    assert "Correctie" in menu.inner_text()
    assert _geen_zijwaartse_scroll(page)


def test_de_bewegingen_hebben_de_juiste_kolommen(webshop_page):
    """The movements columns at 1 440 px: "Wat" no wider than its kind, "Reden"
    the widest; at 390 px no sideways scroll (Koen's fifth point)."""
    page = webshop_page
    page.goto("/admin/voorraad")
    page.locator("tr[data-row] a[data-row-link]").first.click()
    page.wait_for_selector("table.data-table")

    page.set_viewport_size({"width": 1440, "height": 844})
    headers = page.locator("table.data-table th")
    wat = headers.filter(has_text="Wat").bounding_box()
    reden = headers.filter(has_text="Reden").bounding_box()
    assert wat["width"] <= 137, "Wat is breder dan zijn kolomsoort (136 px)"
    assert reden["width"] > wat["width"], "Reden is niet de breedste kolom"

    page.set_viewport_size({"width": 390, "height": 844})
    assert _geen_zijwaartse_scroll(page)
