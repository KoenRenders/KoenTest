"""#727 — "Gepubliceerd" geldt nu ook voor `site-footer` en `home-intro`.

Beide blokken werden op élke publieke pagina getoond, ongeacht het vinkje. Dat was
bewust: `get_page()` haalde ze op "voor blokken die de site zelf invult". Maar het
beheerscherm tóónde dat vinkje wél, dus wie het uitzette verwachtte dat de footer
verdween — en er gebeurde niets. Koen kiest ervoor de vlag te laten gelden, zonder
uitzondering voor blok-pagina's; die uitzondering was juist de verwarring.

**De tests komen in paren.** "Niet gepubliceerd → niet getoond" alleen zou ook
groen staan als het blok voorgoed verdwenen is; dat is dezelfde valkuil als #680.
Pas samen met "gepubliceerd → wél getoond" is het een bewering over de vlag.

De laatste test dekt de val die bij deze wijziging hoort: de footer publiceren
zonder `show_in_nav` uit te zetten levert een menu-item **"site-footer"** in de
publieke navigatie op. Op PROD stond die vlag namelijk op true; dat viel nooit op,
want de navigatie eist `is_published AND show_in_nav`.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (lokaal):
  * `get_published_page` in `site_context` terug op een eigen query zonder de
    publicatievlag → de footertest valt om;
  * idem voor `home-intro` in `cms/ui.py` → de introtest valt om;
  * de `show_in_nav`-regel uit migratie 094 gehaald → de navigatietest valt om.
"""
import pytest

from app.domains.cms.models import CmsPage

pytestmark = pytest.mark.ui_serverrendered

FOOTERTEKST = "Raak Millegem vzw — voettekst"
INTROTEKST = "Welkom op de startpagina"


def _blok(db, slug: str, tekst: str, *, gepubliceerd: bool,
          in_nav: bool = False) -> list[CmsPage]:
    """Zet dit blok in de gevraagde stand — voor ÉLKE rij met deze slug.

    De migraties seeden deze blokken per tenant, dus er staan er meerdere met
    dezelfde slug en het verzoek kiest de zijne. Eén rij aanpassen en dan hopen dat
    het de juiste was, maakt de test afhankelijk van welke `first()` teruggeeft; dat
    is precies hoe een test groen blijft staan terwijl ze iets anders meet dan ze
    beweert.
    """
    rijen = db.query(CmsPage).filter(CmsPage.slug == slug).all()
    if not rijen:
        rijen = [CmsPage(slug=slug, title=slug)]
        db.add(rijen[0])
    for rij in rijen:
        rij.content = f"<p>{tekst}</p>"
        rij.is_published = gepubliceerd
        rij.show_in_nav = in_nav
    db.flush()
    return rijen


# ── De footer ────────────────────────────────────────────────────────────────

def test_een_niet_gepubliceerde_footer_staat_niet_op_de_site(client, db_session):
    _blok(db_session, "site-footer", FOOTERTEKST, gepubliceerd=False)

    resp = client.get("/")

    assert resp.status_code == 200
    assert FOOTERTEKST not in resp.text


def test_een_gepubliceerde_footer_staat_er_wel(client, db_session):
    """De tegenhanger. Zonder haar zou "footer voorgoed weg" ook groen staan."""
    _blok(db_session, "site-footer", FOOTERTEKST, gepubliceerd=True)

    resp = client.get("/")

    assert FOOTERTEKST in resp.text


# ── De home-intro ────────────────────────────────────────────────────────────

def test_een_niet_gepubliceerde_intro_staat_niet_op_de_homepagina(client, db_session):
    _blok(db_session, "home-intro", INTROTEKST, gepubliceerd=False)

    resp = client.get("/")

    assert resp.status_code == 200
    assert INTROTEKST not in resp.text


def test_een_gepubliceerde_intro_staat_er_wel(client, db_session):
    _blok(db_session, "home-intro", INTROTEKST, gepubliceerd=True)

    assert INTROTEKST in client.get("/").text


# ── De val: publiceren zonder de navigatievlag uit te zetten ─────────────────

def test_een_gepubliceerde_footer_hoort_niet_in_het_menu(client, db_session):
    """Dit is de reden dat migratie 094 twee regels heeft.

    De navigatie eist `is_published AND show_in_nav`. Op PROD stond de footer op
    `show_in_nav = true`; zolang `is_published` onwaar was viel dat niet op. Publiceer
    je hem zonder het tweede, dan verschijnt er een menu-item "site-footer" — het ene
    gerepareerd, het andere gebroken.
    """
    _blok(db_session, "site-footer", FOOTERTEKST, gepubliceerd=True, in_nav=False)

    resp = client.get("/")

    assert "site-footer" not in resp.text, (
        "de footer staat als menu-item in de publieke navigatie")


def test_de_migratie_publiceert_de_twee_blokken_en_haalt_de_footer_uit_het_menu(
        db_session):
    """De datastap zelf. Zonder haar verdwijnen footer en intro bij de deploy.

    De suite draait de migratie vóór er data is, dus de SQL wordt hier op eigen
    rijen uitgevoerd — zoals bij 093.
    """
    import importlib.util
    from pathlib import Path

    from sqlalchemy import text

    pad = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
           / "094_publiceer_de_siteblokken.py")
    spec = importlib.util.spec_from_file_location("migratie_094", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # De beginsituatie zoals op PROD gemeten: allebei onzichtbaar, footer in het menu.
    _blok(db_session, "home-intro", INTROTEKST, gepubliceerd=False, in_nav=False)
    _blok(db_session, "site-footer", FOOTERTEKST, gepubliceerd=False, in_nav=True)

    db_session.execute(text(f"""
        UPDATE cms.cms_pages SET is_published = true
         WHERE slug IN {module.SLUGS} AND is_published IS DISTINCT FROM true"""))
    db_session.execute(text("""
        UPDATE cms.cms_pages SET show_in_nav = false
         WHERE slug = 'site-footer' AND show_in_nav IS DISTINCT FROM false"""))

    db_session.expire_all()
    intros = db_session.query(CmsPage).filter(CmsPage.slug == "home-intro").all()
    footers = db_session.query(CmsPage).filter(CmsPage.slug == "site-footer").all()
    assert intros and footers, "de blokken bestaan niet"
    assert all(p.is_published for p in intros + footers), (
        "de blokken zijn niet gepubliceerd")
    assert not any(p.show_in_nav for p in footers), (
        "de footer staat na de migratie nog als menu-item aan")
