"""E2E #1207 — de maat van een pagina-afbeelding, en of ze een rondgang overleeft.

Twee dingen die alleen een browser kan zeggen, en de eerste is de reden dat dit
issue bestaat.

**1. De maat moet de TWEEDE bewaring overleven.** De editor maakt van élke `<img>`
een bijlage en houdt daarbij alleen bron, breedte en hoogte over — gemeten bij
#1173. Een maat die je als klasse of als `width` op de afbeelding schrijft, staat
er na het invoegen netjes op en is weg zodra iemand de pagina opnieuw opent en
nog eens bewaart. Dat is stil: de eerste bewaring ziet er goed uit. Deze test
doet precies die rondgang — invoegen, opslaan, opnieuw openen, iets anders
wijzigen, opnieuw opslaan — en kijkt dan pas.

**2. De drie maten renderen werkelijk verschillend.** Gemeten op de gerenderde
pagina en niet op de klassenaam: een klasse die nergens een regel heeft, staat
keurig in de HTML en doet niets.

Gemeten waarden op een venster van 1440 px, tekstkolom 1248 px: klein **412**,
half **624**, vol **1248**. Op 390 px, kolom **358**: alle drie **358** — daar
vervalt de maat, want een halve kolom is er 179 px en een schermafdruk met tekst
is dan onleesbaar. Die keuze staat in `site_base.html` bij de regels zelf.

**Een breed testbeeld en niet dat van de seed.** `max-width` vergroot niets, dus
met het 240 px-seedbeeld renderen klein, half en vol alle drie 240 px en meet je
niets. Dat is bij het bouwen één keer misgegaan en het leverde een meting op die
er geldig uitzag.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
- `size: maat || "vol"` uit de `Trix.Attachment` in `admin_pagina.html` gehaald →
  de rondgangtest valt om met de bijlage-JSON in de melding;
- de drie `.cms-beeld-*`-regels uit `site_base.html` gehaald en de pagina
  herladen → de maattest valt om met drie keer dezelfde breedte.
"""
import json
import os
import re
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, Paginascherm, login_met_sessie  # noqa: E402

ALT = "Schermafdruk van het aanmeldformulier"


def _ontbreekt(reden: str) -> None:
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e-seed geladen maar: {reden}")
    pytest.skip(reden)


@pytest.fixture(scope="module")
def admin_page():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
        login_met_sessie(page, make_session_value(email))
        yield page
        browser.close()


def _bijlage(inhoud: str) -> dict:
    match = re.search(r'data-trix-attachment="([^"]*)"', inhoud)
    assert match, f"de editor bewaarde geen bijlage:\n{inhoud}"
    return json.loads(match.group(1).replace("&quot;", '"'))


def test_de_maat_overleeft_een_tweede_bewaring(admin_page):
    """De test waar dit issue om draait.

    Niet "staat de maat er na het invoegen" — dat zou ook slagen met de maat als
    klasse op de `<img>`, en precies dán verdwijnt ze bij de volgende bewaring.
    """
    scherm = Paginascherm(admin_page).open_eerste()
    if scherm is None:
        _ontbreekt("geen cms-pagina op deze omgeving")

    admin_page.get_by_role("button", name="Afbeelding").first.click()
    dialoog = admin_page.get_by_role("dialog")
    expect(dialoog, "het dialoogje ging niet open").to_be_visible()
    keuze = dialoog.locator("button[data-url]").first
    if keuze.count() == 0:
        _ontbreekt("geen pagina-afbeelding in de bibliotheek")

    keuze.click()
    dialoog.locator("#cp-alt").fill(ALT)
    dialoog.get_by_role("button", name="Klein").click()
    dialoog.get_by_role("button", name="Invoegen").click()

    # Eerste bewaring — hier ziet alles er ook goed uit met een kapotte oplossing.
    na_invoegen = _bijlage(scherm.editorinhoud())
    assert na_invoegen.get("size") == "klein", (
        f"de maat staat niet in de bijlage-JSON: {na_invoegen}")
    scherm.opslaan()

    paginaid = re.search(r"/admin/paginas/(\d+)", admin_page.url)
    assert paginaid, admin_page.url

    # ── De rondgang: opnieuw openen, iets ANDERS wijzigen, opnieuw opslaan ──
    admin_page.goto(f"/admin/paginas/{paginaid.group(1)}")
    admin_page.wait_for_selector("#cp-trix", timeout=10000)
    # Een merkbare string zónder voorloopspatie. Met " x" wachtte deze test zich
    # dood: Trix schrijft een leidende spatie weg als `&nbsp;`, dus die tekst
    # staat nooit letterlijk in de verborgen invoer. Gemeten bij #1173 en hier
    # één keer opnieuw tegengekomen.
    admin_page.evaluate(
        "() => document.getElementById('cp-trix').editor.insertString('zz')")
    # Wachten op de voorwaarde en niet op de klok (#997): de editor schrijft zijn
    # HTML in de verborgen invoer, en pas wanneer die wijziging er staat heeft
    # opslaan zin.
    admin_page.wait_for_function(
        "() => document.getElementById('cp-content-input').value.includes('zz')",
        timeout=5000)
    scherm.opslaan()

    na_rondgang = _bijlage(scherm.editorinhoud())
    assert na_rondgang.get("size") == "klein", (
        "de maat is bij de tweede bewaring verdwenen — ze staat dus niet in de "
        f"bijlage-gegevens maar op de <img>: {na_rondgang}")
    assert na_rondgang.get("alt") == ALT, (
        f"de alt van #1173 sneuvelde op dezelfde rondgang: {na_rondgang}")

    # En wat de bezoeker ziet.
    admin_page.goto(f"/admin/paginas/{paginaid.group(1)}/voorbeeld")
    beeld = admin_page.locator("img.cms-beeld-klein")
    expect(beeld.first, "de maatklasse staat niet op de gerenderde pagina"
           ).to_be_visible()


@pytest.fixture(scope="module")
def drie_maten():
    """Een eigen pagina met dezelfde brede afbeelding op de drie maten."""
    from io import BytesIO

    from PIL import Image

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.cms.api import CmsPage
    from app.domains.media.api import MediaAsset

    buf = BytesIO()
    Image.new("RGB", (1600, 900), (230, 236, 245)).save(buf, format="PNG")
    breed = buf.getvalue()

    db = SessionLocal()
    asset = MediaAsset(kind="page_image", title="E2E breed testbeeld", data=breed,
                       content_type="image/png", thumbnail=breed,
                       thumb_content_type="image/png", width=1600, height=900,
                       byte_size=len(breed), sort_order=0, is_active=True)
    db.add(asset)
    db.flush()

    def figuur(maat: str) -> str:
        velden = (f"&quot;alt&quot;:&quot;Beeld {maat}&quot;,"
                  "&quot;contentType&quot;:&quot;image&quot;,"
                  f"&quot;size&quot;:&quot;{maat}&quot;,"
                  f"&quot;url&quot;:&quot;/api/v1/media/{asset.id}&quot;")
        return (f'<div><figure data-trix-attachment="{{{velden}}}" '
                f'data-trix-content-type="image">'
                f'<img src="/api/v1/media/{asset.id}"></figure></div>')

    pagina = CmsPage(title="E2E maatmeting", slug="e2e-maatmeting",
                     content="".join(figuur(m) for m in ("klein", "half", "vol")),
                     is_published=True)
    db.add(pagina)
    db.commit()
    slug = pagina.slug
    db.close()
    return slug


def _breedtes(page, slug: str, breedte: int) -> dict:
    page.set_viewport_size({"width": breedte, "height": 900})
    page.goto(f"/{slug}")
    page.wait_for_selector(".cms-content img", timeout=10000)
    return page.evaluate("""() => {
      const kolom = document.querySelector('.cms-content');
      const uit = {kolom: Math.round(kolom.getBoundingClientRect().width)};
      for (const img of kolom.querySelectorAll('img')) {
        uit[img.getAttribute('alt')] = Math.round(img.getBoundingClientRect().width);
      }
      return uit;
    }""")


def test_de_drie_maten_renderen_verschillend(admin_page, drie_maten):
    """Gemeten op de pagina en niet op de klassenaam: een klasse zonder regel
    staat keurig in de HTML en doet niets."""
    m = _breedtes(admin_page, drie_maten, 1440)

    assert m["Beeld klein"] < m["Beeld half"] < m["Beeld vol"], (
        f"de drie maten renderen niet oplopend: {m}")
    assert m["Beeld vol"] == m["kolom"], (
        f"volle breedte vult de kolom niet: {m}")
    # Geen van de drie steekt buiten de kolom — `max-width:100%` blijft gelden.
    for naam in ("Beeld klein", "Beeld half", "Beeld vol"):
        assert m[naam] <= m["kolom"], f"{naam} is breder dan de kolom: {m}"


def test_op_een_telefoon_vervalt_de_maat(admin_page, drie_maten):
    """De keuze uit #1207, en ze staat ook in `site_base.html` bij de regels.

    Een halve kolom is op 390 px ongeveer 179 px; een schermafdruk met tekst is
    dan onleesbaar, en dat is nu juist waarvoor deze beelden bedoeld zijn.
    """
    m = _breedtes(admin_page, drie_maten, 390)

    for naam in ("Beeld klein", "Beeld half", "Beeld vol"):
        assert m[naam] == m["kolom"], (
            f"{naam} staat op een telefoon niet op volle breedte: {m}")
