"""Eén naam en één icoon voor Raakje (#1117).

Gevraagd door Koen op 21 september 2026. Er stonden drie benamingen voor dezelfde
assistent en geen enkele droeg een icoon: *AI · Betalingen*, *AI · Activiteit* en
*Vraag het Raakje*. Nu heet elke ingang `AI · <Scherm>` met het `sparkles`-icoon
vóór het label, uit de kit — en het achtervoegsel zegt wat de reikwijdte is:

| Naam | Betekent |
|---|---|
| `AI · Activiteit` | Raakje, hier, over déze activiteit |
| `AI · Betalingen` | Raakje, hier, over deze selectie betalingen |
| `AI · Raakje` | Raakje zelf — geen scherm, geen selectie |

Daarom `AI · Raakje` en géén `AI · Rapporten`: de beheer-assistent beantwoordt
vragen over betalingen, leden, activiteiten en taken. Hem onder *Rapporten*
parkeren verkleint hem tot één van zijn onderwerpen — vandaar ook zijn eigen
menu-item in *Inzicht*, naast Dashboard en Rapporten.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
`lead_icon="sparkles"` van de overlayknop weggehaald → de eerste test valt om en
noemt de knop bij naam (`AI · Activiteit`, `AI · Betalingen`); het menu-item uit
de groep *Inzicht* gehaald → de menutest valt om.
"""
from __future__ import annotations

import re

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from tests._reporting_seed import TENANT_A
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

# Een herkenbaar stuk van het Lucide-pad, niet het hele pad: een test die op de
# laatste decimaal let, breekt bij elke Lucide-update zonder dat er iets mis is.
STERRETJES = 'd="M12 3 10.1 8.8'
ONDERTITEL = ("Stel een vraag over de eigen cijfers in gewone zinnen. Raakje "
              "draait er een echt rapport voor — het verzint geen getallen.")


def _login(client, db) -> str:
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    bestaand = {r.role_code for r in user.roles}
    for rol in ("ADMIN", "OPERATOR", "FINANCE"):
        if rol not in bestaand:
            db.add(UserRole(user_id=user.id, role_code=rol))
    db.flush()
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


@pytest.fixture
def assistent_aan(db_session, monkeypatch):
    from app.config import settings
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    set_setting(db_session, "admin_chat_enabled", "1", tenant_id=TENANT_A)
    db_session.flush()


def _inhoud(html: str) -> str:
    """Alleen het scherm zelf, zonder de schil.

    De linkernavigatie draagt sinds #1117 óók een link `AI · Raakje`, en die staat
    vóór de knop in de uitvoer. Zonder deze afbakening toetst de icoontest de
    menulink — die geen icoon heeft en er ook geen hoort te hebben.
    """
    start = html.find("<main")
    assert start != -1, "geen <main> in de uitvoer"
    return html[start:]


def _knop_met(html: str, label: str) -> str:
    """De gerenderde knop (of link) met dit label, inclusief haar inhoud."""
    treffer = re.search(
        r"<(button|a)\b[^>]*>(?:(?!</\1>).)*?" + re.escape(label) + r"(?:(?!</\1>).)*?</\1>",
        _inhoud(html), re.S)
    assert treffer, f"geen knop met het label {label!r} gevonden"
    return treffer.group(0)


# ── 1. Elke ingang: sparkles + AI · <Scherm> ─────────────────────────────────

def test_elke_raakje_ingang_draagt_het_sterretjesicoon(client, db_session, assistent_aan):
    activiteit, _o, _p = seed_activity_with_product(db_session)
    db_session.flush()
    _login(client, db_session)

    ingangen = [
        (f"/admin/activiteiten/{activiteit.id}", "AI · Activiteit"),
        ("/admin/betalingen", "AI · Betalingen"),
        ("/admin/rapporten", "AI · Raakje"),
    ]
    zonder = []
    for pad, label in ingangen:
        antwoord = client.get(pad)
        assert antwoord.status_code == 200, f"{pad} → {antwoord.status_code}"
        knop = _knop_met(antwoord.text, label)
        if STERRETJES not in knop:
            zonder.append(f"{label} ({pad})")

    assert not zonder, (
        "deze Raakje-ingangen dragen het sparkles-icoon niet: " + ", ".join(zonder)
        + " — gebruik lead_icon=\"sparkles\" op de kitknop, geen eigen markup")


def test_de_ingangen_heten_ai_plus_hun_onderwerp(client, db_session, assistent_aan):
    """De oude namen zijn weg: `Vraag het Raakje` stond op het rapportenscherm en
    zei niet dat het om dezelfde assistent ging."""
    activiteit, _o, _p = seed_activity_with_product(db_session)
    db_session.flush()
    _login(client, db_session)

    for pad in (f"/admin/activiteiten/{activiteit.id}", "/admin/betalingen",
                "/admin/rapporten", "/admin/rapporten/raakje"):
        html = client.get(pad).text
        assert "Vraag het Raakje" not in html, f"{pad} draagt de oude naam nog"
        assert re.search(r"AI · \w", html), f"{pad} draagt geen AI · …-naam"


def test_het_icoon_komt_uit_de_kit(client, db_session, assistent_aan):
    """Geen losse `<svg>` in een sjabloon: het pad staat één keer, in `_macros.html`."""
    from pathlib import Path

    templates = Path(__file__).resolve().parents[1] / "app"
    in_sjablonen = [str(p.relative_to(templates)) for p in templates.rglob("templates/*.html")
                    if STERRETJES in p.read_text()]
    assert in_sjablonen == ["ui/templates/_macros.html"], in_sjablonen


# ── 2. De assistent heeft zijn eigen menuplek ────────────────────────────────

def test_ai_raakje_staat_in_de_groep_inzicht():
    from app.ui import admin_nav

    groepen = {g["label"]: g["items"] for g in admin_nav("/admin/rapporten")}
    assert "Inzicht" in groepen, sorted(groepen)
    labels = [i["label"] for i in groepen["Inzicht"]]
    assert labels == ["Dashboard", "Rapporten", "AI · Raakje"], labels
    assert [i["href"] for i in groepen["Inzicht"]][-1] == "/admin/rapporten/raakje"


def test_het_menu_item_licht_op_op_zijn_eigen_pagina(client, db_session, assistent_aan):
    """En Rapporten dan níét: twee opgelichte items zeggen niet waar je bent."""
    from app.ui import admin_nav

    items = {i["href"]: i["active"] for g in admin_nav("/admin/rapporten/raakje")
             for i in g["items"]}
    assert items["/admin/rapporten/raakje"] is True
    assert items["/admin/rapporten"] is False

    _login(client, db_session)
    html = client.get("/admin/rapporten/raakje").text
    assert 'href="/admin/rapporten/raakje"' in html


# ── 3. De pagina zelf ────────────────────────────────────────────────────────

def test_de_pagina_heet_ai_raakje_en_houdt_haar_ondertitel(client, db_session,
                                                           assistent_aan):
    _login(client, db_session)
    html = client.get("/admin/rapporten/raakje").text

    titel = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
    # De omgevingsprefix ("[DEV] …") staat ervóór en hoort niet bij de naam.
    assert "AI · Raakje" in titel and "Vraag het Raakje" not in titel, titel
    kop = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1).strip()
    assert "AI · Raakje" in kop, kop
    # Woordelijk: dat is de zin die Raakjes naam draagt en zijn belofte uitlegt.
    assert ONDERTITEL in html, "de ondertitel is gewijzigd"
