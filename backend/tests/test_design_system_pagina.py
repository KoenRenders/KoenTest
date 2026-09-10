"""#783 — `/admin/design-system` toont de kit, en blijft volledig.

De pagina rendert elke kit-macro met de ECHTE `_macros.html` en de ECHTE `app.css`.
Wat ze vervangt was een nabouw: `docs/design-system.html` had een eigen `<style>`
met 53 kleuren waar `build-css.sh` er 36 kent, en geen enkele kit-macro. Zo'n
document loopt uit de pas zonder dat iemand het merkt — gemeten: de zes
conventiewijzigingen van 8 september belandden alle zes in `ui-conventies.md` en
geen enkele in die gids.

**Wat de volledigheidsgate wél en niet bewijst.** Ze toetst dat elke macro op de
pagina VOORKOMT. Ze kan niet zien of de aanroep representatief is:
`ui.btn_primary()` zonder argumenten zou volstaan en niets voorspellen. Dat verschil
— aanwezig tegenover getrouw — vangen de referentielinks per sectie en een mens die
de pagina naast een echt scherm legt. Die belofte staat daarom ook in de docstring
van de route, niet alleen hier.

**Waarom er een uitzonderingenlijst is.** Vijftien van de 49 macro's hebben geen
eigen uiterlijk: `btn_class` levert een klassenreeks, `icon` wordt door de
iconensectie al volledig getoond, `clipboard_js` en `htmx_ux` zijn scripts, en de
drie hosts (`toast_host`, `confirm_host`, `env_banner`) horen in de schil — twee
toast-hosts op één pagina vangen elkaars toasts op. Ze staan hieronder met reden;
een naam toevoegen mag, maar niet stilzwijgend.

Kapotgemaakt om te controleren dat deze test rood kan worden: de aanroep van
`ui.chips(` uit `design_system.html` gehaald → rood, mét de naam `chips` in de
melding. Teruggezet → groen.
"""
import re
from pathlib import Path

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE, User, UserRole, make_session_value)

pytestmark = pytest.mark.ui_serverrendered

UI = Path(__file__).resolve().parents[1] / "app" / "ui" / "templates"
MACROS = (UI / "_macros.html").read_text()
PAGINA = (UI / "design_system.html").read_text()

# Macro's zonder eigen uiterlijk, elk met de reden waarom ze geen demo krijgen.
GEEN_DEMO = {
    "btn_class": "levert een klassenreeks, geen element — staat als tekst bij de knoppen",
    "button": "de generieke vorm; de vier btn_*-varianten tonen hem",
    "icon": "de iconensectie toont de volledige set al",
    "clipboard_js": "script, geen component",
    "htmx_ux": "script, geen component",
    "toast_host": "hoort in de schil; twee hosts op één pagina vangen elkaars toasts op",
    "confirm_host": "idem — de schil draagt hem",
    "toast_oob": "een out-of-band antwoordfragment, geen zichtbaar element op deze pagina",
    "env_banner": "de schil toont hem al bovenaan elke omgeving behalve PROD",
    "card": "het omhulsel van elke sectie hieronder — overal in gebruik",
    "page_header": "staat bovenaan deze pagina zelf",
    "section_header": "scheidt de secties van deze pagina zelf",
    "loading": "staat in de sectie 'Leeg en ladend'",
    "empty_state": "idem",
    "search": "staat in de filterbalk van het lijstscherm",
}


def _macronamen() -> set[str]:
    namen = set(re.findall(r"^\{% macro ([a-z_0-9]+)\(", MACROS, re.M))
    assert len(namen) > 40, (
        f"maar {len(namen)} macro's gevonden — leest deze gate wel `_macros.html`?")
    return {n for n in namen if not n.startswith("_")}


def test_elke_macro_heeft_een_demo():
    ontbreekt = sorted(
        naam for naam in _macronamen()
        if naam not in GEEN_DEMO and f"ui.{naam}(" not in PAGINA)

    assert not ontbreekt, (
        "deze macro's staan niet op /admin/design-system, dus de pagina veroudert "
        f"zoals de oude HTML deed: {ontbreekt}")


def test_de_uitzonderingen_bestaan_nog():
    """Een uitzondering voor een macro die niet meer bestaat, verbergt een gat.

    Zonder deze test blijft `GEEN_DEMO` groeien met namen die niemand meer kent, en
    dan dekt de lijst op den duur meer af dan ze uitlegt.
    """
    verdwenen = sorted(set(GEEN_DEMO) - _macronamen())

    assert not verdwenen, (
        f"deze namen staan in de uitzonderingenlijst maar niet meer in de kit: {verdwenen}")


def test_elke_veldsoort_heeft_een_voorbeeld():
    """#811 — de formuliersoorten zijn geen kit-macro, dus de macro-gate zag ze niet.

    Gemeten op de eerste versie van deze pagina: geen radio-optielijst, geen
    "anders"-optie, en `rating` stond er alleen als woord. Vier van de vijf
    bevindingen van #811 waren onzichtbaar voor een poort die macronamen telt — deze
    tweede poort dekt de soorten af.

    De voorbeelden worden gerenderd door dezelfde `veld()`-macro als het publieke
    formulier (`_formulier_veld.html`), niet nagebouwd. Dat het een eigen partial
    werd, is de structurele helft van diezelfde belofte.

    Kapotgemaakt om te controleren dat deze test rood kan worden: het
    `radio`-voorbeeld uit `_voorbeeldvelden()` gehaald → rood mét die soort.
    """
    from app.domains.forms.models import FIELD_TYPES
    from app.ui.design_system_ui import _voorbeeldvelden

    getoond = {v.field_type for v in _voorbeeldvelden()}
    ontbreekt = sorted(set(FIELD_TYPES) - getoond)

    assert FIELD_TYPES, "geen veldsoorten gevonden — kijkt deze gate wel ergens?"
    assert not ontbreekt, (
        f"deze veldsoorten hebben geen voorbeeld op /admin/design-system: {ontbreekt}")


def test_de_veldsoorten_komen_uit_de_echte_formuliertemplate():
    """Niet nagebouwd — een kopie hier zou precies de afdrijving worden die deze
    pagina moet uitsluiten."""
    assert '{% from "_formulier_veld.html" import veld with context %}' in PAGINA


def test_de_referentielinks_zijn_echte_links():
    """#811 — zes secties verwezen naar een echt scherm en geen enkele link werkte.

    `button()` maakt alleen een `<a>` als de PARAMETER `href` gezet is; een href die
    als tekst in `attrs` meekomt, plakt aan een `<button>` en doet niets. Dat is in
    de macro gerepareerd en niet in de aanroepen, want zoals het was had een
    aanroeper geen enkele correcte manier om er een link van te maken.

    Deze links zijn het tegenwicht dat de volledigheidsgate niet kan leveren: zij
    ziet aanwezigheid, de links laten je getrouwheid controleren. Dood zijn ze dus
    niet cosmetisch.

    Kapotgemaakt om te controleren dat deze test rood kan worden: één
    `action_href=` terug naar `'href="…"'` in `action_attrs` → rood.
    """
    import re

    fouten = [r.strip()[:80] for r in PAGINA.splitlines()
              if "section_header(" in r and 'href="' in r and "action_href=" not in r]

    assert not fouten, (
        "deze secties zetten een href in `action_attrs`; dat levert een <button> met "
        f"een href-attribuut op en die doet niets:\n  " + "\n  ".join(fouten))
    assert PAGINA.count("action_href=") >= 6, (
        "er zijn minder referentielinks dan de zes die #783 belooft")


def test_de_typografiesectie_beschrijft_bestaande_klassen():
    """#811 — deze sectie is handgeschreven en kan dus wél afdrijven.

    De knoppen hieronder komen uit `btn_class` en kunnen niet uit de pas lopen; de
    typeschaal is geen macro maar losse klassen per template. Zonder deze poort
    blijft de pagina de oude maten beweren zodra een template verandert.

    Dat dit geen theorie is, blijkt uit #810: juist omdát de schaal geen macro is,
    moest elk voorkomen apart langs — en `btn_class` werd overgeslagen.

    De poort herbouwt de sectie niet; ze controleert alleen dat elke maat die de
    sectie noemt, ergens in de templates voorkomt die ze beschrijft.

    Kapotgemaakt om te controleren dat deze test rood kan worden: `data-schaal` op
    een verzonnen maat (`text-9xl`) gezet → rood mét die klasse.
    """
    import re
    from pathlib import Path

    genoemd = re.findall(r'data-schaal="([^"]+)"', PAGINA)
    assert len(genoemd) >= 4, (
        f"maar {len(genoemd)} maten gevonden in de typografiesectie — leest deze "
        "gate ze nog wel?")

    app = Path(__file__).resolve().parents[1] / "app"
    templates = [p for p in app.rglob("*.html") if p.name != "design_system.html"]
    assert len(templates) > 50, "de glob vindt te weinig templates"
    alles = "\n".join(p.read_text() for p in templates)

    ontbreekt = [k for k in genoemd if k not in alles]
    assert not ontbreekt, (
        "de typografiesectie noemt maten die in geen enkel template meer voorkomen, "
        f"dus deze pagina beweert iets ouds: {ontbreekt}")


def test_de_pagina_heeft_geen_eigen_stijl():
    """Nul eigen `<style>`: dezelfde app.css als elk beheerscherm.

    Een tweede stijlbron is precies hoe de oude gids 53 kleuren kon tonen waar de
    build er 36 kende.
    """
    # Zonder Jinja-commentaar: het commentaar bovenaan legt juist uit waarom er
    # geen eigen stijl is, en die zin mag de test niet doen omvallen.
    zonder_uitleg = re.sub(r"\{#.*?#\}", "", PAGINA, flags=re.S)

    assert "<style" not in zonder_uitleg.lower()


def _sessie(client, db_session, email, *rollen):
    u = User(email=email, is_active=True)
    db_session.add(u)
    db_session.flush()
    for r in rollen:
        db_session.add(UserRole(user_id=u.id, role_code=r))
    db_session.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def test_zonder_sessie_geen_toegang(client):
    client.cookies.clear()
    resp = client.get("/admin/design-system", follow_redirects=False)

    assert resp.status_code in (401, 302, 303, 307), resp.status_code


def test_een_beheerder_ziet_de_pagina(client, db_session):
    """ADMIN of OPERATOR, op elke omgeving — en bewust niet OPERATOR-only.

    `require_operator_ui(db, email)` heeft een sessie nodig, en dan zou de route
    `db` moeten aannemen. Precies de eigenschap die dit scherm moet bewijzen is dat
    het zónder databank werkt: het toont geen data, alle demo-waarden staan in het
    sjabloon. Er valt hier dus niets te beschermen dat verder gaat dan "niet
    publiek".
    """
    _sessie(client, db_session, "ds-admin@example.com", "ADMIN")

    resp = client.get("/admin/design-system")

    assert resp.status_code == 200
    assert "Design system" in resp.text
    # Een paar componenten die er echt gerenderd horen te staan, geen macronamen:
    assert "Opslaan" in resp.text and "Openstaand" in resp.text


def test_de_gerenderde_pagina_toont_geen_ontsnapte_html(client, db_session):
    """#815 — de poorten hierboven tellen namen in de BRON; deze kijkt naar de uitvoer.

    Twee defecten van Koens tweede ronde ontstonden pas bij het renderen en waren dus
    onzichtbaar voor elke brontest:

    * een vertaalde tekst in een `~`-concatenatie escapete de hele control, waardoor
      er letterlijk `&lt;textarea` op het scherm stond. Gemeten in Jinja: met
      autoescape escapet `~` de ándere operanden zodra er één `Markup` tussen staat,
      en `_()` levert `Markup`;
    * `row_actions` kreeg tuples in plaats van kant-en-klare HTML en drukte
      `('Bewerken', 'href=…')` af.

    Deze test vangt de hele klasse en niet die twee gevallen: alles wat als
    ontsnapte tag of als Python-repr in de uitvoer belandt, valt op.

    Kapotgemaakt om te controleren dat deze test rood kan worden: `.format()` in
    `field_select` terug naar `~`-concatenatie → rood op `&lt;select`; de acties in
    `row_actions` terug naar tuples → rood op de tuple-vorm.
    """
    _sessie(client, db_session, "ds-render@example.com", "ADMIN")

    html = client.get("/admin/design-system").text

    ontsnapt = [t for t in ("&lt;textarea", "&lt;select", "&lt;option", "&lt;input",
                            "&lt;button", "&lt;a ") if t in html]
    assert not ontsnapt, (
        f"deze tags staan als tekst op de pagina in plaats van gerenderd: {ontsnapt}")

    # Let op de vorm: `row_actions` doet `{{ a|safe }}`, dus een tuple belandt
    # ONGE-escaped in de uitvoer — met `Markup('…')` en al. Zoeken naar `&#39;` (mijn
    # eerste poging) vond dus niets, terwijl het defect er wel degelijk stond.
    import re

    reprs = [t for t in ("(Markup(", "Markup('") if t in html]
    reprs += re.findall(r"\('[^']{1,40}', '[^']{1,80}'\)", html)
    assert not reprs, (
        f"er staan Python-waarden op de pagina; een macro kreeg het verkeerde soort "
        f"argument: {reprs[:3]}")


def test_de_kleurtokens_komen_uit_de_gegenereerde_css(client, db_session):
    """Niet overgetypt — dát was de fout van de oude gids.

    De tokens worden uit `:root` in `app.css` gelezen, dus als de build ze wijzigt,
    wijzigt deze pagina mee zonder dat iemand iets bijwerkt.
    """
    _sessie(client, db_session, "ds-admin2@example.com", "OPERATOR")

    resp = client.get("/admin/design-system")

    assert resp.status_code == 200
    assert "var(--" in resp.text, "er wordt geen enkel token uit de CSS getoond"


def test_systeeminfo_verwijst_naar_de_pagina(client, db_session):
    """#783 punt 3b — anders vindt niemand haar.

    Een scherm dat alleen bestaat als je het pad kent, wordt niet gebruikt, en dan
    veroudert het precies zoals de HTML-gids die het vervangt. De volledigheidsgate
    houdt de pagina volledig; deze link houdt haar in gebruik.

    Systeeminfo is de juiste plek en niet zomaar een plek: die gaat over het systeem
    en niet over de gegevens, net als het design system. Ze draaien allebei op
    `require_admin_ui`, dus de link kan nooit naar een 403 wijzen — bij een
    OPERATOR-only keuze was dat wél gebeurd voor elke ADMIN.

    Kapotgemaakt om te controleren dat deze test rood kan worden: het blok uit
    `admin_info.html` gehaald → rood.
    """
    _sessie(client, db_session, "ds-info@example.com", "ADMIN")

    resp = client.get("/admin/info")

    assert resp.status_code == 200
    assert "/admin/design-system" in resp.text, (
        "Systeeminfo verwijst niet naar het design system")
