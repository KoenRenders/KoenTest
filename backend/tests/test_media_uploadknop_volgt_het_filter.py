"""De uploadknop volgt het filter, ook zonder paginalading (#1138 punt 2).

Koen op HDEV: staat hij op *Sponsorlogo* en klikt hij **+ Uploaden**, dan landt
hij bij activiteitenfoto's. Op *Activiteitenfoto* klopt het wel.

**De oorzaak is de vorm van het scherm, niet de knop.** De filterbalk doet een
`hx-get` met `hx-target="#me-lijst"` en vervangt dus alléén de kaarten. De knop
staat in de paginakop, búiten dat doel: haar `href` wordt server-side gebouwd bij
het LADEN van de pagina en daarna nooit meer bijgewerkt. Klik je een chip aan,
dan wisselen de kaarten en blijft de knop op de soort van bij het laden staan.

**En daarom neemt deze test de weg van de gebruiker en niet die van de URL.**
Mijn eerste meting vroeg `/admin/media?kind=sponsor` rechtstreeks op — een
volledige paginalading — en dáár klopte alles. Twee wegen naar hetzelfde scherm,
een verschillende uitkomst, en de weg die hij elke dag neemt was niet de gemeten
weg. Een test die `?kind=…` opvraagt, laat precies dit gat bestaan.

De reparatie is dezelfde als bij de recordkop van een activiteit (#748/#714): het
fragment stuurt de knop out-of-band mee.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):

- het oob-blok uit `_me_lijst.html` halen → *na een chipklik* valt om, en de
  melding toont de oude soort in de href;
- `oob_uploadknop` ook op de paginaroute zetten → *de pagina zet de knop niet
  dubbel* valt om;
- `_filterstand` de activiteit ook bij een sponsorlogo laten meesturen → de
  laatste test valt om, die de regel uit die docstring bewaakt.
"""
from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

SOORTEN = ("sponsor", "activity_photo", "tenant_logo")


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _uploadlinks(html: str) -> list[str]:
    return [h.replace("&amp;", "&")
            for h in re.findall(r'href="(/admin/media/nieuw[^"]*)"', html)]


def _chipklik(client, kind: str, extra: str = "") -> str:
    """Wat de filterbalk doet als je een soort-chip aanklikt.

    `hx-target="#me-lijst"`, dus het antwoord is het fragment — en alles wat
    daarbuiten moet bijwerken, moet erin meereizen.
    """
    antwoord = client.get(
        f"/admin/media?kind={kind}{extra}",
        headers={"HX-Request": "true",
                 "HX-Current-URL": "http://testserver/admin/media"})
    assert antwoord.status_code == 200
    return antwoord.text


@pytest.mark.parametrize("kind", SOORTEN)
def test_na_een_chipklik_wijst_de_knop_naar_de_gekozen_soort(client, db_session,
                                                              kind):
    """De test die het gemelde gedrag vangt.

    Bewust ná een paginalading met een ANDERE soort: dat is de volgorde waarin
    Koen het zag, en zonder die eerste stap zou de knop toevallig goed kunnen
    staan.
    """
    _login(client)
    client.get("/admin/media")            # laadt met activity_photo als standaard

    fragment = _chipklik(client, kind)

    links = _uploadlinks(fragment)
    assert links, ("het fragment draagt geen uploadknop — dan blijft de knop op "
                   "de pagina staan zoals ze bij het laden gebouwd werd")
    assert all(f"kind={kind}" in link for link in links), links


def test_de_knop_reist_out_of_band_en_niet_als_losse_link(client, db_session):
    """Hoe ze meereist doet ertoe: zonder `hx-swap-oob` landt ze ín de lijst.

    Dan staat er een tweede knop tussen de kaarten in plaats van dat de knop in
    de kop bijgewerkt wordt — groen op "er staat een link", fout op het scherm.
    """
    _login(client)
    client.get("/admin/media")

    fragment = _chipklik(client, "sponsor")

    assert 'id="me-uploadknop" hx-swap-oob="true"' in fragment


def test_de_pagina_zet_de_knop_niet_dubbel(client, db_session):
    """De tegenhanger: op een volledige lading rendert het sjabloon de knop zelf.

    Zou het oob-blok daar óók meekomen, dan staat de knop er twee keer — en dat
    is precies wat de vlag voorkomt.
    """
    _login(client)

    pagina = client.get("/admin/media").text

    assert len(_uploadlinks(pagina)) == 1, _uploadlinks(pagina)
    assert "hx-swap-oob" not in pagina


# ── Punt 3: uploaden vanaf een activiteit ────────────────────────────────────

def test_vanaf_een_activiteit_staat_die_activiteit_al_ingevuld(client, db_session):
    """De handeling die Koen het vaakst doet (#1138 punt 3).

    Vandaag moest hij de activiteit die hij net bekeek opnieuw opzoeken in een
    lijst. De knop in de recordkop draagt haar mee, zelfde vorm als de sprong
    naar de Design Studio ernaast — en de soort staat er expliciet bij, want
    vanaf een activiteit is dat per definitie een activiteitenfoto.
    """
    from app.domains.activities.api import Activity

    activiteit = Activity(name="Gezinsuitstap Irrland", location="Irrland")
    db_session.add(activiteit)
    db_session.flush()
    _login(client)

    kop = client.get(f"/admin/activiteiten/{activiteit.id}").text
    links = _uploadlinks(kop)

    assert links == [f"/admin/media/nieuw?kind=activity_photo"
                     f"&activity_id={activiteit.id}"], links

    # En de bestemming doet er ook iets mee: soort én activiteit staan gekozen.
    formulier = client.get(links[0]).text
    assert re.search(r'<option value="activity_photo" selected', formulier)
    assert re.search(rf'<option value="{activiteit.id}"[^>]*selected', formulier), (
        "de activiteit staat niet voorgekozen in het uploadformulier")


def test_een_sponsorlogo_krijgt_geen_activiteit_mee(client, db_session):
    """De regel uit `_filterstand` blijft staan (#1138 testpunt 4).

    Bij een sponsorlogo betekent een activiteit niets; ze zou als parameter
    blijven rondslingeren. Deze test staat hier omdat punt 3 van hetzelfde issue
    — uploaden vanaf een activiteit — die regel stilletjes zou kunnen opheffen.
    """
    _login(client)
    client.get("/admin/media")

    fragment = _chipklik(client, "sponsor", extra="&activity_id=1")

    links = _uploadlinks(fragment)
    assert links and all("activity_id" not in link for link in links), links
