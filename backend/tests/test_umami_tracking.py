"""#808 — Umami mat niets meer sinds de React-exit.

In v1.14 rende `frontend/src/components/Analytics.tsx` het trackingscript. Bij de
React-exit (#405) verdween dat zonder Jinja-vervanger, en niemand merkte het: er
faalde niets, er kwam alleen geen data meer binnen.

Gemeten in de Umami-databank van PROD: laatste geregistreerde bezoek op 9 september
2026 om 17:41 UTC, 33 bezoeken die dag daarvóór, **nul** sinds 19:00 UTC. Dat uur is
precies de omschakeling waarbij de gedeelde Caddy de pagina's van `prod-frontend`
naar `prod-backend` stuurde — de meting stopte op het moment dat de server-rendered
stack het overnam.

**De derde test is de belangrijkste.** Zonder haar is "het script staat in de
basis-template" niet te onderscheiden van "het script staat in de JUISTE
basis-template", en beheerverkeer zou meetellen als bezoek.

De tweede test dekt de halve instelling af. Een scripttag met een lege `src` doet een
verzoek dat nergens heen gaat; een lege `data-website-id` rapporteert aan niets.
Allebei zien ze er in de broncode uit alsof er wél iets gebeurt, en dat is precies de
verwarring die dit issue veroorzaakte.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden, en twee van de
drie pogingen leverden een correctie op mijn eigen aanname op:

* het scriptblok uit `site_base.html` gehaald → de eerste valt om. Zoals verwacht.
* de `and` in `umami_tracking()` vervangen door `or` → de tweede blijft GROEN. De
  halve instelling wordt namelijk twee keer tegengehouden: door die functie én door
  de `{% if %}` in de schil. Dat is bewuste dubbele bescherming — `umami_tracking()`
  voedt óók het Systeeminfo-scherm, waar "beide gezet" iets anders moet betekenen
  dan "er staat tekst" — maar het betekent dat deze test gedrag toetst en niet één
  implementatiedetail. Beide guards tegelijk weghalen maakt hem wel rood.
* het blok naar `admin_base.html` gekopieerd → de derde bleef eerst óók groen, en
  dat was leerzaam: de beheerschil krijgt `umami_src` helemaal niet in haar context,
  dus de tag rendert daar leeg. Pas met de tag én de contextsleutels erbij valt de
  test om. Het script kan vandaag dus alleen in de beheerschil belanden als iemand
  twee dingen tegelijk doet — en dán vangt deze test het.
"""
import pytest

from app.domains.auth.api import (
    SESSION_COOKIE, User, UserRole, make_session_value)
from app.kernel.tenant_config import set_setting

pytestmark = pytest.mark.ui_serverrendered

SRC = "https://stats.voorbeeld.test/script.js"
WEBSITE_ID = "11111111-2222-3333-4444-555555555555"


def _stel_in(db_session, src=SRC, website_id=WEBSITE_ID):
    set_setting(db_session, "umami_src", src or None)
    set_setting(db_session, "umami_website_id", website_id or None)
    db_session.commit()


def _beheerder(client, db_session, email="umami@example.com"):
    u = User(email=email, is_active=True)
    db_session.add(u)
    db_session.flush()
    db_session.add(UserRole(user_id=u.id, role_code="ADMIN"))
    db_session.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def test_een_publieke_pagina_draagt_het_script(client, db_session):
    _stel_in(db_session)

    html = client.get("/").text

    assert SRC in html, "het trackingscript staat niet op de publieke pagina"
    assert f'data-website-id="{WEBSITE_ID}"' in html, (
        "het script rapporteert niet aan het juiste website-id")


@pytest.mark.parametrize("src,website_id", [
    (SRC, ""),      # wel een script, maar het rapporteert aan niets
    ("", WEBSITE_ID),  # wel een id, maar er wordt niets geladen
    ("", ""),
])
def test_een_halve_instelling_levert_geen_script(client, db_session, src, website_id):
    """Beide of geen van beide — een halve tag meet niets en ziet er wél uit alsof."""
    _stel_in(db_session, src, website_id)

    html = client.get("/").text

    assert "data-website-id" not in html, (
        f"er staat een scripttag met src={src!r} en id={website_id!r}")
    assert "script.js" not in html


def test_een_beheerpagina_draagt_het_script_niet(client, db_session):
    """De tegenproef die ertoe doet: beheerverkeer is geen bezoek.

    Zonder haar zou een script in de verkeerde schil er in de tests net zo uitzien
    als een script in de juiste, en zouden de cijfers stil vervuild raken met ons
    eigen klikken.
    """
    _stel_in(db_session)
    _beheerder(client, db_session)

    html = client.get("/admin/info").text

    assert "data-website-id" not in html, "de beheerschil draagt het trackingscript"
    assert SRC not in html


def test_systeeminfo_zegt_of_er_echt_gemeten_wordt(client, db_session):
    """De vlag hoort te zeggen wat er gebeurt, niet of er tekst staat.

    Vóór #808 rekende dit scherm zelf `bool(src and id)` uit en meldde
    "geconfigureerd" — terwijl er nergens een script gerenderd werd. Beide kanten
    staan hier, want alleen samen tonen ze dat de vlag echt iets volgt.
    """
    _beheerder(client, db_session, "umami2@example.com")

    _stel_in(db_session, SRC, "")
    assert "meet niet" in client.get("/admin/info").text

    _stel_in(db_session)
    assert "meet mee" in client.get("/admin/info").text
