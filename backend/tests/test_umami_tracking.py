"""#808 — Umami mat niets meer sinds de React-exit.

In v1.14 rende `frontend/src/components/Analytics.tsx` het trackingscript. Bij de
React-exit (#405) verdween dat zonder Jinja-vervanger, en niemand merkte het: er
faalde niets, er kwam alleen geen data meer binnen.

Gemeten in de Umami-databank van PROD: laatste geregistreerde bezoek op 9 september
2026 om 17:41 UTC, 33 bezoeken die dag daarvóór, **nul** sinds 19:00 UTC. Dat uur is
precies de omschakeling waarbij de gedeelde Caddy de pagina's van `prod-frontend`
naar `prod-backend` stuurde — de meting stopte op het moment dat de server-rendered
stack het overnam.

**Twee schillen, niet één.** `site_base.html` en `public_base.html` erven niet van
elkaar; de tweede draagt alleen `/raakje`. Het script in één schil zetten maakt
precies één pagina blind, en dat is onzichtbaar in de cijfers. Beide staan daarom in
de parametrisering.

**De tegenproef op de beheerschil is de belangrijkste.** Zonder haar is "het script staat in de
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


# Er zijn TWEE publieke schillen en ze erven niet van elkaar: `site_base.html`
# (veertien templates) en `public_base.html` (alleen `/raakje`). Het script alleen in
# de eerste zetten maakt precies één pagina blind, en dat merk je nooit — de cijfers
# zien er verder normaal uit.
PUBLIEKE_PAGINAS = ["/", "/raakje"]


@pytest.mark.parametrize("pad", PUBLIEKE_PAGINAS)
def test_elke_publieke_schil_draagt_het_script(client, db_session, pad, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "chat_enabled", True)
    _stel_in(db_session)

    html = client.get(pad).text

    assert SRC in html, f"{pad} draagt het trackingscript niet"
    assert f'data-website-id="{WEBSITE_ID}"' in html, (
        f"{pad} rapporteert niet aan het juiste website-id")


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


# ── De gate: elke publieke schil draagt het blok ─────────────────────────────

# Wélke soort schil het trackingscript hoort te dragen. De verzameling schillen zelf
# wordt AFGELEID (elk template dat een volledig document is), niet opgesomd: een gate
# die `site_base.html` en `public_base.html` bij naam noemt vangt de fout van vandaag
# maar niet die van morgen — en die van morgen is een dérde schil waar niemand aan
# denkt, precies hoe `public_base.html` vandaag over het hoofd gezien is.
#
# Een onbekende soort maakt de gate rood. Zo dwingt hij geen momentopname af maar een
# beslissing: wie een schil toevoegt, zegt erbij of ze meetelt.
SCHILSOORTEN = {
    "site": True,       # de publieke site — veertien templates
    "public": True,     # /raakje, een eigen schil die NIET van site_base erft
    "platform": False,  # eigen domein; tenant-cijfers zouden vervuild raken
    "admin": False,     # beheerverkeer is geen bezoek
    "afdruk": False,    # papier, en de route eronder is een beheerscherm
}


def _schillen() -> dict:
    """Elk template dat een volledig document is, met zijn `data-shell`-soort."""
    import re
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app"
    gevonden = {}
    for pad in list(app.rglob("*.html")):
        tekst = pad.read_text()
        if "<!DOCTYPE" not in tekst:
            continue
        soort = re.search(r'data-shell="([a-z]+)"', tekst)
        gevonden[pad] = soort.group(1) if soort else None
    return gevonden


def test_de_gate_vindt_uberhaupt_schillen():
    """#678: een gate die niets vindt, staat voorgoed groen.

    Verhuist de templatemap of wijzigt de manier waarop een schil herkenbaar is, dan
    hoort deze poort te vallen in plaats van stilzwijgend niets meer te bewaken.
    """
    schillen = _schillen()

    assert len(schillen) >= 4, (
        f"maar {len(schillen)} volledige documenten gevonden — kijkt deze gate nog "
        "wel op de juiste plaats?")


def test_elk_volledig_document_zegt_wat_voor_schil_het_is():
    """Zonder `data-shell` kan de gate niet beslissen, en dan raadt hij."""
    zonder = sorted(str(p.name) for p, soort in _schillen().items() if soort is None)

    assert not zonder, (
        f"deze documenten dragen geen data-shell: {zonder}. Voeg er een toe en zet "
        "de soort in SCHILSOORTEN, met de reden waarom ze wel of niet meetelt.")


def test_elke_publieke_schil_bevat_het_analytics_blok():
    """En de niet-publieke juist niet.

    **Wat deze gate NIET bewijst:** dat een `hx-boost`-navigatie geteld wordt. Dat is
    gedrag van Umami's script en geen eigenschap van onze templates. Een groene poort
    zegt hier alleen "de tag staat er" — precies het onderscheid dat `umami_configured`
    vóór #808 verkeerd maakte, en dat is het hele punt van dit issue.

    (Gemeten uit het script dat onze eigen Umami serveert: het vervangt
    `history.pushState`/`replaceState` door een wrapper die bij een échte
    URL-wijziging een pageview inplant, en auto-track staat aan tenzij je
    `data-auto-track="false"` zet. htmx boost navigeert via `pushState`. Dat is een
    meting op een image-versie, geen garantie voor elke toekomstige versie — dus ze
    staat hier als opmerking en niet als assertie.)

    Kapotgemaakt om te controleren dat deze gate rood kan worden: het
    `{% include "_umami.html" %}` uit `public_base.html` gehaald → rood mét die
    bestandsnaam.
    """
    ontbreekt, teveel = [], []
    for pad, soort in _schillen().items():
        if soort not in SCHILSOORTEN:
            continue  # de vorige test meldt dit al, met een bruikbaarder bericht
        heeft = '{% include "_umami.html" %}' in pad.read_text()
        if SCHILSOORTEN[soort] and not heeft:
            ontbreekt.append(pad.name)
        if not SCHILSOORTEN[soort] and heeft:
            teveel.append(pad.name)

    assert not ontbreekt, (
        f"deze publieke schillen meten niets: {sorted(ontbreekt)}")
    assert not teveel, (
        f"deze schillen horen niet mee te tellen maar dragen het script: {sorted(teveel)}")
