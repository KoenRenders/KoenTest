"""Geen `<form>` binnen een `<form>` op een gerenderd scherm (#1115).

Op Betalingen deed *Vraag* niets en lijnden de drie controls niet uit. Eén
oorzaak: de Raakje-overlay werd aangeroepen **binnen** `{% call ui.filter_bar %}`,
en die rendert een `<form … onsubmit="return false">`. De overlay brengt haar
eigen `<form>` mee, en genest mag dat niet: de browser gooit de binnenste tag
weg. De submit-knop hoorde daarna bij de filterbalk — die niets doet — en de
`flex gap-2 items-end` van de weggegooide vorm was verdwenen.

**Deze gate kijkt op de gerenderde uitvoer en niet op de bron**, want in
`_betalingen_scherm.html` alleen is niets te zien: de nesting ontstaat pas
doordat twee sjablonen elkaar insluiten. Zelfde familie als de sluittag met
attributen (#1101), en om dezelfde reden een eigen regel in plaats van een
volledige HTML-validatie: een strikte parser struikelt over de Alpine- en
htmx-attribuutnamen, en een tolerante parser slikt precies dít stil in — hij
herstelt de nesting zoals een browser en meldt niets.

De schermen hieronder renderen mét de beheer-assistent aan, want de overlay is
juist het stuk dat de fout veroorzaakte. Elke render wordt getoetst op 200 én op
de aanwezigheid van minstens één `<form>`: een gate die een foutpagina scant,
vindt vanzelf geen nesting en staat groen om de verkeerde reden (#678).

Kapotgemaakt om te controleren dat deze gate rood kan worden (gemeten): de
Raakje-overlay terug binnen `{% call ui.filter_bar %}` gezet → rood met
`/admin/betalingen` en het regelnummer van de binnenste `<form>`.
"""
from __future__ import annotations

from html.parser import HTMLParser

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from tests._reporting_seed import TENANT_A
from tests.conftest import (SEEDED_ADMIN_EMAIL, create_test_family,
                            seed_activity_with_product, seed_postal_code)

pytestmark = pytest.mark.ui_serverrendered


class _Nesting(HTMLParser):
    """Elke `<form>` die opent terwijl er al één open staat."""

    def __init__(self):
        super().__init__()
        self.diepte = 0
        self.fouten: list[int] = []

    def handle_starttag(self, tag, attrs):
        if tag != "form":
            return
        self.diepte += 1
        if self.diepte > 1:
            self.fouten.append(self.getpos()[0])

    def handle_endtag(self, tag):
        if tag == "form":
            self.diepte = max(0, self.diepte - 1)


def _login(client, db) -> str:
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    bestaand = {r.role_code.value for r in user.roles}  # CR-12 fase 2
    for rol in ("ADMIN", "OPERATOR", "FINANCE"):
        if rol not in bestaand:
            db.add(UserRole(user_id=user.id, role_code=rol))
    db.flush()
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


@pytest.fixture
def assistent_aan(db_session, monkeypatch):
    """Beide schakelaars aan (CR-07 §6.3): zonder deze staat de overlay er niet,
    en dan toetst deze gate het scherm zonder het stuk dat de fout gaf."""
    from app.config import settings
    from app.kernel.tenant_config import set_setting

    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    set_setting(db_session, "admin_chat_enabled", "1", tenant_id=TENANT_A)
    db_session.flush()


@pytest.fixture
def schermen(client, db_session, assistent_aan) -> list[str]:
    """De paden die deze gate afloopt, met net genoeg data om echt te renderen."""
    _login(client, db_session)
    seed_postal_code(db_session)
    activiteit, _onderdeel, _product = seed_activity_with_product(db_session)
    gezin, _persoon = create_test_family(db_session, email="genest@example.com")
    db_session.flush()
    return [
        "/admin/betalingen",
        f"/admin/activiteiten/{activiteit.id}",
        f"/admin/activiteiten/{activiteit.id}/betalingen",
        f"/admin/leden/gezin/{gezin.id}",
        "/admin/leden",
        "/admin/leden/nieuw",
        "/admin/activiteiten",
        "/admin/rapporten",
        "/admin/rapporten/nieuw",
        "/admin/gebruikers",
        "/admin/e-maillog",
    ]


def test_geen_enkel_scherm_rendert_een_formulier_in_een_formulier(client, schermen):
    assert len(schermen) >= 8, "de schermenlijst kromp; deze gate scant bijna niets"

    fouten = []
    for pad in schermen:
        antwoord = client.get(pad)
        assert antwoord.status_code == 200, f"{pad} → {antwoord.status_code}"
        assert "<form" in antwoord.text, (
            f"{pad} rendert geen enkel formulier — dan bewijst deze scan niets")
        meter = _Nesting()
        meter.feed(antwoord.text)
        for regel in meter.fouten:
            fouten.append(f"{pad}:{regel}")

    assert not fouten, (
        "Een <form> binnen een <form>: de browser gooit de binnenste tag weg, "
        "waarna zijn knoppen bij het buitenste formulier horen en zijn opmaak "
        "verdwenen is (#1115). Zet het binnenste formulier ernaast:\n  "
        + "\n  ".join(fouten))


def test_de_betalingen_overlay_staat_buiten_de_filterbalk(client, schermen):
    """De plek waar het misging, apart: de knop hoort niet in het filterformulier.

    Een structurele toets naast de scan hierboven, want deze zegt *waarom* het
    fout was — de filterbalk draagt `onsubmit="return false"`, dus een submit-knop
    die erbij hoort doet gegarandeerd niets.
    """
    html = client.get("/admin/betalingen").text
    assert "AI · Betalingen" in html, "voorwaarde: de overlay staat op het scherm"

    filterbalk = html.index('id="bt-filter"')
    einde = html.index("</form>", filterbalk)
    assert "AI · Betalingen" not in html[filterbalk:einde], (
        "de Raakje-knop staat binnen het filterformulier; daar submit hij niets")
