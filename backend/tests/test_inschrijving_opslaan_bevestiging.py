"""#717 — "Opslaan" sluit het inschrijvingspaneel en bevestigt met een toast.

Het paneel bleef na Opslaan in bewerkmodus staan, zonder enig teken dat er iets
bewaard was: dezelfde velden, dezelfde knop. Niet toevallig — `edit_open=True`
is bewust gezet in #613-3, omdat het fragment zichzelf via outerHTML vervangt en
anders na élke actie dichtklapte. Voor de tussenacties klopt die redenering; voor
de afsluitende handeling niet.

**Waarom deze tests op de vlaggen toetsen en niet op de statuscode.** `assert
resp.status_code == 200` slaagde vóór deze wijziging net zo goed — dat is de
valkuil uit #680. Wat verandert is de stand van twee vlaggen, dus daar kijken we:
de `edit`-stand in de `x-data` en de aan- of afwezigheid van het oob-attribuut.

De laatste twee tests zijn de rem: ze leggen de #613-3-invariant vast. Zonder hen
zou "sluiten na een actie" ongemerkt naar de tussenacties kunnen doorlekken, en dat
is precies de bug die #613-3 destijds oploste.

Kapotgemaakt om te controleren dat elke test rood kán worden — het succespad in
`inschrijving_opslaan` teruggezet op de oude regel (`edit_open=True, ververs=True`,
geen `toast=`):
  * test_opslaan_sluit_het_paneel → faalt op `edit: true`;
  * test_opslaan_bevestigt_met_een_toast → faalt, geen oob-attribuut;
  * test_de_toast_staat_top_level_in_het_antwoord → faalt, geen toast gevonden;
  * de drie tests die het zwijgen van de andere wegen bewaken blijven groen — die
    hangen aan de andere kant van de vlag en horen niet mee te bewegen.
"""
from html.parser import HTMLParser

import pytest

from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from app.domains.activities.api import RegistrationItem
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

# Deze tests hangen aan de gerenderde Jinja/htmx-stand (de `edit`-vlag in de
# x-data en het oob-attribuut), niet aan het domein — dus ui_serverrendered.
pytestmark = pytest.mark.ui_serverrendered

# Het contract uit de macro-commentaar: de aanroeper hangt dit attribuut zelf aan
# de toast. Eén letterlijke string, zodat een test faalt zodra iemand het contract
# aan één van beide kanten wijzigt.
OOB = 'hx-swap-oob="afterbegin:#toasts"'
PANEEL_DICHT = 'x-data="{ edit: false }"'
PANEEL_OPEN = 'x-data="{ edit: true }"'


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _inschrijving(client, db):
    activity, comp, product = seed_activity_with_product(db, is_free=False)
    resp = client.post(f"/api/v1/activities/{activity.id}/register", json={
        "contact_name": "An Janssens", "phone": "0470000000", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}]})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"], product


def _opslaan(client, reg_id, hdr, **velden):
    data = {"contact_name": "An Janssens", "phone": "0470000000", "contact_email": "an@example.com",
            "remarks": ""}
    data.update(velden)
    return client.post(f"/admin/inschrijvingen/{reg_id}/opslaan",
                       headers=hdr, data=data)


# ── Het succespad ────────────────────────────────────────────────────────────

def test_opslaan_sluit_het_paneel(client, db_session):
    """Openblijven gaf hetzelfde scherm terug als vóór de klik."""
    reg_id, _product = _inschrijving(client, db_session)
    resp = _opslaan(client, reg_id, _login(client))

    assert resp.status_code == 200, resp.text
    assert PANEEL_DICHT in resp.text, "het paneel hoort na Opslaan in leesmodus"
    assert PANEEL_OPEN not in resp.text


def test_opslaan_bevestigt_met_een_toast(client, db_session):
    """Sluiten alleen volstaat niet: dan zie je leesmodus zonder bevestiging."""
    reg_id, _product = _inschrijving(client, db_session)
    resp = _opslaan(client, reg_id, _login(client))

    assert OOB in resp.text, "de toast wordt niet out-of-band meegestuurd"
    assert "opgeslagen" in resp.text.lower()


def test_de_toast_staat_top_level_in_het_antwoord(client, db_session):
    """Structureel, niet op tekstvolgorde.

    De toast hoort naast het paneel te staan en niet erin: het paneel is precies
    wat via `outerHTML` vervangen wordt. Een assert op de plaats van de string in
    de tekst zou hier meebewegen met elke opmaakwijziging; de nestdiepte niet.
    """
    reg_id, _product = _inschrijving(client, db_session)
    resp = _opslaan(client, reg_id, _login(client))

    dieptes = _oob_dieptes(resp.text)
    assert dieptes == [0], f"oob-element(en) op nestdiepte {dieptes}, verwacht [0]"


# ── De foutweg blijft zoals ze was ───────────────────────────────────────────

def test_een_validatiefout_houdt_het_paneel_open_zonder_toast(client, db_session):
    """Je bent dan nog bezig; dichtklappen zou de fout uit beeld halen."""
    reg_id, _product = _inschrijving(client, db_session)
    resp = _opslaan(client, reg_id, _login(client), contact_email="geen-adres")

    assert resp.status_code == 200, resp.text
    assert PANEEL_OPEN in resp.text, "het paneel hoort open te blijven bij een fout"
    assert 'role="alert"' in resp.text, "de foutbanner ontbreekt"
    assert OOB not in resp.text, "een mislukte opslag mag niets bevestigen"


# ── De #613-3-invariant: de tussenacties blijven open en zwijgen ─────────────

def test_de_tussenacties_houden_het_paneel_open(client, db_session):
    """`/totaal`, `/regels` en `/regels/{id}/verwijderen` zijn geen afsluiting.

    Deze test hangt aan de andere kant van de vlag uit #717 en hoort dus NIET mee
    te bewegen. Zakt hij door, dan is "sluiten na Opslaan" doorgelekt naar de
    tussenstappen — de bug die #613-3 oploste.
    """
    reg_id, product = _inschrijving(client, db_session)
    hdr = _login(client)
    item_id = (db_session.query(RegistrationItem)
               .filter(RegistrationItem.registration_id == reg_id).one().id)

    wegen = [
        (f"/admin/inschrijvingen/{reg_id}/totaal", {f"quantity_{item_id}": "3"}),
        (f"/admin/inschrijvingen/{reg_id}/regels",
         {"product_id": str(product.id), "quantity": "1"}),
        (f"/admin/inschrijvingen/{reg_id}/regels/{item_id}/verwijderen", {}),
    ]
    for pad, data in wegen:
        resp = client.post(pad, headers=hdr, data=data)
        assert resp.status_code == 200, f"{pad}: {resp.text}"
        assert PANEEL_OPEN in resp.text, f"{pad} liet het paneel dichtklappen"
        assert OOB not in resp.text, f"{pad} stuurde een bevestiging mee"


def test_de_detailroute_levert_geen_toast(client, db_session):
    """Ditzelfde fragment wordt ook zonder actie gerenderd — dan is er niets
    gebeurd om te bevestigen."""
    reg_id, _product = _inschrijving(client, db_session)
    resp = client.get(f"/admin/inschrijvingen/{reg_id}", headers=_login(client))

    assert resp.status_code == 200, resp.text
    assert OOB not in resp.text
    assert PANEEL_DICHT in resp.text, "zonder bewerking hoort het paneel dicht"


# ── Hulpje ───────────────────────────────────────────────────────────────────

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}


class _Dieptemeter(HTMLParser):
    """Noteert op welke nestdiepte elk `hx-swap-oob`-element staat (0 = top-level)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.diepte = 0
        self.gevonden: list[int] = []

    def handle_starttag(self, tag, attrs):
        if any(naam == "hx-swap-oob" for naam, _waarde in attrs):
            self.gevonden.append(self.diepte)
        if tag not in _VOID:
            self.diepte += 1

    def handle_startendtag(self, tag, attrs):
        if any(naam == "hx-swap-oob" for naam, _waarde in attrs):
            self.gevonden.append(self.diepte)

    def handle_endtag(self, tag):
        if tag not in _VOID:
            self.diepte = max(0, self.diepte - 1)


def _oob_dieptes(html: str) -> list[int]:
    meter = _Dieptemeter()
    meter.feed(html)
    return meter.gevonden
