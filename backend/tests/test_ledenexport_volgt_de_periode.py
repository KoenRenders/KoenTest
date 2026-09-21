"""De ledenexport volgt de gekozen periode, ook zonder paginalading (#1141).

De knop **Ledenexport (.ods) voor Raak Nationaal** staat in de paginakop en
draagt de periode in haar adres. De filterbalk doet een `hx-get` met
`hx-target="#lw-inhoud"` en vervangt dus alléén de tabel; de knop staat
daarbuiten en haar `href` wordt gebouwd bij het LADEN van de pagina. Zet je de
periode op "sinds 2020" en klik je dan Exporteren, dan krijg je de wijzigingen
van de laatste dertig dagen — de standaard van bij het laden.

**Waarom dit erger is dan hetzelfde geval op /admin/media (#1138 punt 2):** daar
land je op het verkeerde uploadscherm en zie je dat meteen. Hier krijg je een
bestand dat eruitziet alsof het klopt, zonder iets op het scherm dat zegt welke
periode erin zit. En dit is het bestand dat naar Raak Nationaal gaat.

**Daarom neemt deze test de weg van de gebruiker en niet die van de URL.** De
exportlink rechtstreeks opvragen is een ándere weg en precies waarom dit zo lang
stond: die weg werkte altijd al. De test leest de link uit het FRAGMENT dat de
filterbalk terugkrijgt, en downloadt hem dan.

Gemeten vóór de reparatie (21 september 2026), via die echte weg:

    na paginalading:                 /admin/ledenwijzigingen/export?since=<vandaag-30>
    na filterwissel naar 2020-01-01:
        exportlinks in het fragment: []      ← komt niet mee
        oob-velden in het fragment:  2       ← wél voor sort en richting

Het mechanisme was er dus al (`_lw_inhoud.html` stuurt `lw-sort` en
`lw-richting` out-of-band mee); de exportknop was er alleen nooit in opgenomen.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):

- het oob-blok uit `_lw_inhoud.html` halen → de eerste twee tests vallen om,
  met "geen exportlink in het fragment — de knop blijft op de oude periode
  staan";
- `oob_exportknop` óók op de paginaroute zetten → *de pagina zet de knop niet
  dubbel* valt om met twee identieke links, en de eerste test valt mee om op
  de paginalading. Dat laatste is meegenomen: de eerste test bewaakt dus ook
  dat de knop niet verdubbelt.

De vierde test stond vanaf het begin groen en hoort dat ook: ze pint een
gemeten eigenschap van de route vast, niet iets dat gerepareerd werd.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime, timedelta, timezone

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_postal_code

pytestmark = pytest.mark.ui_serverrendered

OUD = "2020-01-01"


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _exportlinks(html: str) -> list[str]:
    return [h.replace("&amp;", "&")
            for h in re.findall(r'href="(/admin/ledenwijzigingen/export[^"]*)"', html)]


def _filterwissel(client, since: str) -> str:
    """Wat de filterbalk doet als je de periode wijzigt.

    `hx-target="#lw-inhoud"`, dus het antwoord is het tabelfragment — en alles
    wat daarbuiten moet bijwerken, moet erin meereizen.
    """
    antwoord = client.get(
        "/admin/ledenwijzigingen", params={"since": since},
        headers={"HX-Request": "true",
                 "HX-Current-URL": "http://testserver/admin/ledenwijzigingen"})
    assert antwoord.status_code == 200, antwoord.text
    return antwoord.text


def _tekst_van_ods(inhoud: bytes) -> str:
    """De platte tekst van het werkblad, zodat een naam erin terug te vinden is."""
    with zipfile.ZipFile(io.BytesIO(inhoud)) as z:
        xml = z.read("content.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", " ", xml)


def _twee_perioden(client, db_session) -> tuple[str, str]:
    """Eén wijziging uit 2020 en één van vandaag.

    Zonder die twee perioden bewijst de export niets: één rij komt bij elke
    `since` mee en dan is een verkeerde periode onzichtbaar.

    Alle historie terugzetten en pas dáárna de tweede persoon maken, in plaats
    van de rijen van één gezin te verhuizen: `member_changes_since` leest uit
    een vijftiental historietabellen, en een persoon laat er bij registratie
    in meerdere tegelijk een spoor na (persoon, adres, contact, lidmaatschap).
    Ik verzette eerst alleen `PersonHistory` — de oude naam bleef dan via zijn
    contactrij in een export van vandaag staan.
    """
    seed_postal_code(db_session)

    def maak(voornaam: str) -> None:
        resp = client.post("/api/v1/families", json={
            "street": "Milostraat", "house_number": "40", "postal_code": "2400",
            "payment_method": "transfer",
            "members": [{"last_name": "Wijziging", "first_name": voornaam,
                         "email": f"{voornaam.lower()}@example.com",
                         "mobile": "0470111111",
                         "date_of_birth": "1980-01-01", "gender_code": "M",
                         "relation_type": "HOOFDLID"}],
        })
        assert resp.status_code == 201, resp.text

    maak("Oud")
    verzet = _alle_historie_naar(db_session, datetime(2020, 6, 1, tzinfo=timezone.utc))
    assert verzet, "geen historierijen verzet — dan meet deze test niets"
    maak("Vers")
    return "Vers", "Oud"


def _alle_historie_naar(db_session, wanneer: datetime) -> int:
    """Zet elke bestaande historierij op `wanneer`; geeft het aantal terug.

    Loopt over de mappers in plaats van over een lijst modelnamen: die lijst zou
    stil achterlopen zodra de export een tabel erbij krijgt, en dan zou de test
    groen blijven terwijl ze een periode minder toetst.
    """
    from app.database import Base

    verzet = 0
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if not model.__name__.endswith("History") or not hasattr(model, "recorded_at"):
            continue
        for rij in db_session.query(model).all():
            rij.recorded_at = wanneer
            verzet += 1
    db_session.flush()
    return verzet


def test_na_een_filterwissel_draagt_de_knop_de_nieuwe_periode(client, db_session):
    """De test die het gemelde gedrag vangt.

    Bewust ná een paginalading met de standaardperiode: dat is de volgorde
    waarin het misgaat, en zonder die eerste stap zou de knop toevallig goed
    kunnen staan.
    """
    _login(client)
    pagina = client.get("/admin/ledenwijzigingen")
    assert pagina.status_code == 200
    standaard = (date.today() - timedelta(days=30)).isoformat()
    assert _exportlinks(pagina.text) == [
        f"/admin/ledenwijzigingen/export?since={standaard}"], \
        "de paginakop hoort de standaardperiode te dragen"

    links = _exportlinks(_filterwissel(client, OUD))
    assert links, "geen exportlink in het fragment — de knop blijft op de oude periode staan"
    assert links == [f"/admin/ledenwijzigingen/export?since={OUD}"], \
        f"de exportknop draagt niet de gekozen periode: {links}"


def test_het_bestand_bevat_de_rijen_van_de_gekozen_periode(client, db_session):
    """De test die telt: de knop kan het juiste adres dragen terwijl de route
    iets anders doet. Daarom wordt de link uit het fragment ook echt gevolgd."""
    _login(client)
    vers, oud = _twee_perioden(client, db_session)

    client.get("/admin/ledenwijzigingen")

    ruim = _exportlinks(_filterwissel(client, OUD))
    assert ruim, "geen exportlink in het fragment na de wissel naar 2020"
    breed = client.get(ruim[0])
    assert breed.status_code == 200, breed.text
    tekst = _tekst_van_ods(breed.content)
    ontbreekt = [n for n in (vers, oud) if n not in tekst]
    assert not ontbreekt, (
        f"sinds {OUD} horen beide wijzigingen in het bestand te staan, "
        f"ontbreken: {ontbreekt}")

    # En de tegenhanger: een korte periode laat de oude rij WEG. Zonder deze
    # helft zou een export die alles teruggeeft ook groen staan.
    kort = _exportlinks(_filterwissel(client, date.today().isoformat()))
    assert kort, "geen exportlink in het fragment na de wissel naar vandaag"
    smal = client.get(kort[0])
    assert smal.status_code == 200, smal.text
    tekst_smal = _tekst_van_ods(smal.content)
    assert vers in tekst_smal, "de wijziging van vandaag hoort er wél in te staan"
    assert oud not in tekst_smal, \
        "een export vanaf vandaag mag de wijziging uit 2020 niet bevatten"


def test_de_pagina_zet_de_knop_niet_dubbel(client, db_session):
    """Het oob-blok hoort alleen in het FRAGMENT te zitten.

    Zou de paginaroute het ook zetten, dan stonden er twee knoppen met dezelfde
    id op het scherm — en dan is de tweede stil de eerste aan het overschrijven.
    """
    _login(client)
    pagina = client.get("/admin/ledenwijzigingen")
    assert len(_exportlinks(pagina.text)) == 1, \
        f"de volle pagina hoort één exportknop te tonen: {_exportlinks(pagina.text)}"
    assert 'hx-swap-oob' not in pagina.text.split('id="lw-inhoud"')[0], \
        "de paginakop hoort geen out-of-band blok te dragen"


def test_de_export_filtert_alleen_op_de_periode(client, db_session):
    """Waarom de knop terecht alleen `since` draagt — gemeten, niet aangenomen.

    `ledenwijzigingen_export` neemt één parameter, en `member_changes_since`
    kent alleen een datum: groep en actor filteren de TABEL, niet het bestand.
    Deze test pint dat vast. Gaat de export ooit wél op groep filteren, dan
    draagt de knop stilletjes de verkeerde selectie en hoort dit om te vallen.
    """
    _login(client)
    _twee_perioden(client, db_session)

    kaal = client.get(f"/admin/ledenwijzigingen/export?since={OUD}")
    met_filters = client.get(
        f"/admin/ledenwijzigingen/export?since={OUD}&group=Persoon&actor=niemand")
    assert kaal.status_code == met_filters.status_code == 200
    assert _tekst_van_ods(kaal.content) == _tekst_van_ods(met_filters.content), \
        ("de export reageert op groep of actor — dan draagt de exportknop een "
         "onvolledige selectie en moet ze die filters óók meenemen")
