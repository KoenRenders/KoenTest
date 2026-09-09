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


def test_de_kleurtokens_komen_uit_de_gegenereerde_css(client, db_session):
    """Niet overgetypt — dát was de fout van de oude gids.

    De tokens worden uit `:root` in `app.css` gelezen, dus als de build ze wijzigt,
    wijzigt deze pagina mee zonder dat iemand iets bijwerkt.
    """
    _sessie(client, db_session, "ds-admin2@example.com", "OPERATOR")

    resp = client.get("/admin/design-system")

    assert resp.status_code == 200
    assert "var(--" in resp.text, "er wordt geen enkel token uit de CSS getoond"
