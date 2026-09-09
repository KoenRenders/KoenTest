"""#807 — het dubbele euroteken op de homepage.

De publieke homepage toonde **`€€35,00`**. De seedtekst zet een letterlijke `€` vóór
`{{membership_price_full}}`, en die placeholder levert sinds #579 zélf het
euroteken. Tekst en renderer spraken elkaar tegen, en de bezoeker zag het.

**De test die er echt toe doet is de tweede**, niet die van het gelukkige geval: een
euro die NIET vóór een placeholder staat moet blijven staan. Zonder haar is een
migratie die te gulzig zoekt niet te onderscheiden van een die het goed doet — en een
redacteur mag gewoon `€` typen, bijvoorbeeld in "vanaf € 5 per deelnemer".

Het bewijs van het gelukkige geval staat op het **gerenderde** resultaat en niet op de
opgeslagen tekst: de fout die de bezoeker zag zat in de render, dus daar hoort ze
weg te zijn.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: het patroon
verruimd tot `€(\\s|&nbsp;)*` zonder de placeholder erachter → de tweede test valt om
(de losse euro verdwijnt); de `regexp_replace` vervangen door een no-op → de eerste
en de derde vallen om.
"""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.domains.cms.render import render_cms_content

pytestmark = pytest.mark.ui_serverrendered

def _migratie_095():
    """Op pad inladen — `alembic/versions` is geen package."""
    pad = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
           / "095_euroteken_voor_de_prijsplaceholder.py")
    spec = importlib.util.spec_from_file_location("migratie_095", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migratie = _migratie_095()


def _pagina(db_session, slug: str, inhoud: str):
    from app.domains.cms.models import CmsPage

    pagina = CmsPage(slug=slug, title=slug, content=inhoud, is_published=True)
    db_session.add(pagina)
    db_session.flush()
    return pagina


def _schoon(db_session):
    db_session.execute(text(migratie.schoon_sql()))
    db_session.expire_all()


def test_de_euro_voor_de_placeholder_verdwijnt_uit_de_render(db_session):
    """Het bewijs staat op wat de bezoeker ziet, niet op wat er opgeslagen is."""
    pagina = _pagina(db_session, "e807-intro",
                     "<p>Het lidmaatschap bedraagt €{{membership_price_full}} "
                     "voor een gezin.</p>")
    voor = render_cms_content(pagina.content)
    assert "€€" in voor, f"de fout is niet nagebootst: {voor}"

    _schoon(db_session)

    na = render_cms_content(db_session.get(type(pagina), pagina.id).content)
    assert "€€" not in na, f"het dubbele euroteken staat er nog: {na}"
    assert "€" in na, f"nu is het euroteken helemaal weg: {na}"


@pytest.mark.parametrize("inhoud", [
    "<p>Vanaf € 5 per deelnemer.</p>",
    "<p>Wij rekenen €, geen dollars.</p>",
    "<p>Het bedrag (€) staat op de bevestiging.</p>",
])
def test_een_euro_die_niet_voor_een_placeholder_staat_blijft(db_session, inhoud):
    """De tegenproef, en zonder haar bewijst de vorige test niets.

    Een migratie die élke euro weghaalt haalt de eerste test ook, en sloopt
    ondertussen de tekst van elke redacteur die het teken gewoon gebruikt.
    """
    pagina = _pagina(db_session, f"e807-vrij-{abs(hash(inhoud)) % 10000}", inhoud)

    _schoon(db_session)

    assert db_session.get(type(pagina), pagina.id).content == inhoud, (
        "de opschoning is te gulzig en raakt gewone tekst")


def test_een_tweede_run_verandert_niets(db_session):
    """Idempotent. Een datamigratie draait op elke omgeving opnieuw bij een herstel
    of een replay, en dan mag ze niet verder knippen dan de eerste keer."""
    pagina = _pagina(db_session, "e807-tweemaal",
                     "<p>Lidgeld €{{membership_price_full}}, half "
                     "€ {{ membership_price_half }}.</p>")

    _schoon(db_session)
    na_een = db_session.get(type(pagina), pagina.id).content
    _schoon(db_session)
    na_twee = db_session.get(type(pagina), pagina.id).content

    assert na_een == na_twee, "de tweede run wijzigt de tekst opnieuw"
    assert "€{{" not in na_een and "€ {{" not in na_een, (
        f"de variant met spatie of zonder is blijven staan: {na_een}")


def test_de_seedmigraties_blijven_ongemoeid():
    """027 en 028 wijzigen we niet — een gemergede migratie raak je niet aan.

    Deze test legt vast waaróm er een opruimstap nodig is: de seeds blijven het
    euroteken zetten, dus elke verse omgeving en elke nieuwe tenant loopt er opnieuw
    tegenaan als 095 er niet is.
    """
    versies = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    seed = (versies / "028_cms_home_intro_placeholders.py").read_text()

    assert "€{{membership_price_full}}" in seed, (
        "028 is gewijzigd; een gemergede migratie hoort onaangeroerd te blijven — "
        "de correctie hoort in een nieuwe stap")
