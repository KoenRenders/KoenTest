"""#1160: de footer toont wat ze HERKENT als sociaal netwerk.

Tot deze reparatie stond de regel omgekeerd: de drie bekende netwerken eerst, en
daarna alles wat de module niet kende — op een handgeschreven uitzonderingslijst
``{"EMAIL", "PHONE", "WEBSITE"}`` na. Die lijst miste ``MOBILE``, dus op PROD
stond het mobiele nummer van de vereniging als vierde icoon in de footer van elke
publieke pagina, met het rauwe nummer als ``href``.

Twee fouten, en ze worden hier apart getoetst: de classificatie (wat is een
netwerk?) hoort in de bron, en een waarde die geen URL is hoort nooit in een
``href``. Elke test hieronder is tegen de reparatie in gedraaid; wat er dan
omviel staat in zijn docstring.
"""
from __future__ import annotations

import pytest

from app.domains.mdm.api import (ContactDetail, ContactTypeCode, Organization)
from app.domains.mdm.api import ContactTypeLabel
from app.kernel.tenant_config import _actieve_tenant

pytestmark = pytest.mark.ui_agnostisch

MOBIEL = "0470 99 88 77"


@pytest.fixture
def organisatie(db_session):
    return (db_session.query(Organization)
            .filter(Organization.id == _actieve_tenant(None))
            .execution_options(include_all_tenants=True).one())


def _contact(db_session, organisatie, code: str, waarde: str) -> None:
    db_session.add(ContactDetail(tenant_id=organisatie.id,
                                 organization_id=organisatie.id,
                                 contact_type_code=code, value=waarde))


def _codes(db_session, organisatie) -> list[str]:
    from app.ui import _sociale_links

    return [link["code"] for link in _sociale_links(db_session, organisatie)]


# ── 1. Het gemelde geval ────────────────────────────────────────────────────

def test_the_mobile_number_is_not_a_social_icon(db_session, organisatie, client):
    """Het scherm dat Koen op PROD zag: vier iconen, waarvan één het gsm-nummer.

    Dit is het gemelde geval en het leunt op BEIDE reparaties; wat het niet is,
    is het bewijs van één ervan. Gemeten bij de tegenproef, en het verschil is
    de moeite waard:

    - alleen de classificatie teruggedraaid → deze test blijft **groen**, want
      een gsm-nummer is ook geen geldige URL en de tweede grendel houdt hem
      tegen. Rood werd alleen `test_an_unclassified_type_stays_out_of_the_footer`
      (SIGNAL, mét een geldige URL) — dát is de geïsoleerde proef op de bron.
    - beide teruggedraaid → rood met
      ``['FACEBOOK', 'INSTAGRAM', 'MOBILE', 'TIKTOK']`` in de melding, en het
      nummer in de gerenderde footer.

    Twee grendels voor één fout is hier bedoeld en geen duplicatie: de ene zegt
    wat een netwerk is, de andere wat een link is. Een gsm-nummer valt door
    allebei; een verkeerd ingevuld Facebook-adres alleen door de tweede.

    Het nummer stond trouwens ook in de `sameAs` van het schema.org-blok
    (`site_base.html`), dus het werd twee keer publiek gemaakt.
    """
    _contact(db_session, organisatie, "FACEBOOK", "https://facebook.com/raak")
    _contact(db_session, organisatie, "INSTAGRAM", "https://instagram.com/raak")
    _contact(db_session, organisatie, "TIKTOK", "https://tiktok.com/@raak")
    _contact(db_session, organisatie, "MOBILE", MOBIEL)
    db_session.commit()

    codes = _codes(db_session, organisatie)
    assert "MOBILE" not in codes, (
        f"het gsm-nummer hoort niet tussen de sociale iconen; gekregen: {codes}")
    assert len(codes) == 3, f"drie netwerken verwacht, gekregen: {codes}"

    html = client.get("/aanmelden").text
    assert MOBIEL not in html, (
        "het mobiele nummer staat publiek in de opmaak — het contactblok toont "
        "bewust alleen Telefoon")


def test_the_three_real_networks_survive_in_a_fixed_order(db_session, organisatie):
    """De bescherming naast de vorige test.

    Zonder deze zou een reparatie die de hele icoonrij weggooit óók groen staan:
    "MOBILE zit er niet meer in" is waar zodra er niets meer in zit.
    """
    _contact(db_session, organisatie, "TIKTOK", "https://tiktok.com/@raak")
    _contact(db_session, organisatie, "FACEBOOK", "https://facebook.com/raak")
    _contact(db_session, organisatie, "INSTAGRAM", "https://instagram.com/raak")
    _contact(db_session, organisatie, "MOBILE", MOBIEL)
    db_session.commit()

    assert _codes(db_session, organisatie) == ["FACEBOOK", "INSTAGRAM", "TIKTOK"], (
        "de volgorde komt van de code en niet van de invoervolgorde van de rijen")


# ── 2. De bron classificeert, niet het scherm ───────────────────────────────
#
# Dat een VIJFDE netwerk nog altijd één rij is (de belofte van #945) staat in
# `test_organisatie_lijsten.py::test_a_fifth_network_is_only_a_row_in_the_code_list`
# en niet hier — die test bestond al en hoort bij het issue dat de vorm koos.

def test_every_contact_type_is_classified(db_session):
    """De poort op de bron: een contactsoort zonder classificatie bestaat niet.

    Dit is wat #1160 structureel afsluit. Een achtste contactsoort die morgen
    door een migratie wordt toegevoegd, moet zeggen wát ze is; zwijgt ze, dan
    valt deze test om met haar code in de melding — in plaats van dat ze een
    maand later in de footer opduikt.

    Kapotgemaakt om te bewijzen dat hij rood kan worden: de classificatie van
    ``WEBSITE`` op NULL gezet; de test faalde met
    *"niet geclassificeerd: ['WEBSITE']"*. Daarna hersteld.

    De eerste assertie is er omdat een poort die niets vindt ook niets afkeurt
    (zie MEMORY: een poort telt eerst haar treffers).
    """
    rijen = (db_session.query(ContactTypeCode)
             .execution_options(include_all_tenants=True).all())
    assert len(rijen) >= 7, (
        f"de poort kijkt naar niets: {len(rijen)} contactsoorten gevonden, "
        "de seeds leveren er zeven")

    ongeclassificeerd = sorted(r.code for r in rijen if r.is_social_network is None)
    assert not ongeclassificeerd, (
        f"contactsoort(en) niet geclassificeerd: {ongeclassificeerd} — zet "
        "`is_social_network` in de migratie die de soort toevoegt, anders weet "
        "de footer niet of ze een icoon verdient")


def test_an_unclassified_type_stays_out_of_the_footer(db_session, organisatie):
    """De andere kant van dezelfde rij: zwijgen is géén icoon.

    De poort hierboven vangt dit in CI, maar op een draaiende omgeving telt wat
    de footer doet. NULL rendert als "geen netwerk" — dat is precies de default
    die #1160 omdraaide.
    """
    # CR-12 phase 2: code and label are two rows. `is_social_network` stays
    # NULL, and that is exactly what this test wants: not classified.
    db_session.add(ContactTypeCode(code="SIGNAL", sort_order=81,
                                   is_active=True))
    db_session.add(ContactTypeLabel(code="SIGNAL", language="nl",
                                    value="Signal"))
    db_session.flush()
    _contact(db_session, organisatie, "SIGNAL", "https://signal.example/raak")
    db_session.commit()

    assert "SIGNAL" not in _codes(db_session, organisatie), (
        "een contactsoort die niet zegt dat ze een netwerk is, hoort niet tussen "
        "de iconen te staan")


# ── 3. Een waarde die geen URL is, wordt nooit een href ─────────────────────

@pytest.mark.parametrize("waarde", [
    "0470 99 88 77",                 # het gemelde geval
    "www.facebook.com/raak",         # vergeten schema — leest als relatief pad
    "/raakvoorbeeld",                # al een pad
    "raak@example.com",              # geen link maar een adres
    "javascript:alert(1)",           # en geen ander schema dan http(s)
])
def test_a_value_that_is_no_url_never_becomes_a_link(db_session, organisatie,
                                                     client, waarde):
    """De tweede helft van #1160, en ze hangt aan de LINK en niet aan de soort.

    Ook een écht netwerk met een verkeerd ingevulde waarde levert anders een
    relatief pad op: de browser maakt er `https://<ons domein>/<de waarde>` van.
    Getoetst op FACEBOOK — een code die de bron wél als netwerk kent, zodat deze
    test niet stiekem op de classificatie leunt.

    Tegenproef: met de URL-controle eruit slaagt geen enkele parameter.
    """
    _contact(db_session, organisatie, "FACEBOOK", waarde)
    db_session.commit()

    assert _codes(db_session, organisatie) == [], (
        f"{waarde!r} is geen absolute http(s)-URL en hoort dus geen href te worden")
    assert f'href="{waarde}"' not in client.get("/aanmelden").text


def test_a_real_url_still_becomes_a_link(db_session, organisatie, client):
    """De tegenhanger: de controle mag de gewone gevallen niet opeten.

    Zonder deze test zou een `_externe_url` die altijd None teruggeeft alle
    tests hierboven groen laten.
    """
    _contact(db_session, organisatie, "FACEBOOK", "http://facebook.com/raak")
    db_session.commit()

    html = client.get("/aanmelden").text
    assert 'href="http://facebook.com/raak"' in html
