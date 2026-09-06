"""#712 — de kop en het instellingenpaneel van de formulierbouwer.

Vier dingen in hetzelfde blok.

1. **"Instellingen" heette niet "Bewerken" en toggelde niet.** Koen zocht naar
   "Bewerken" omdat hij wist dat daar iets zou openklappen; §2.8 schrijft dat paar
   ook voor. De kit heeft er een macro voor die twee schermen verderop in ditzelfde
   bestand al op de veldkaart stond — een handgemaakte knop ernaast is precies hoe
   die twee uit elkaar lopen.
2. **De leesbare link kostte een hele regel** als eigen blok, en duwde alles omlaag.
3. **Twee tekstvakken stonden op `rows=2`**, smaller dan de kit-standaard; iemand had
   die actief teruggezet. De omschrijving van een *sectie* blijft wél op 2 — korte
   toelichting, geen lopende tekst.
4. **De korte velden stonden uit elkaar getrokken**, gescheiden door een tekstvak over
   de volle breedte.

**Waar deze tests op letten.** Zoeken op het woord "Bewerken" bewijst niets: dat komt
op deze pagina ook bij elke veldkaart voor, dus zo'n test staat groen zonder dat déze
knop veranderd is. En de laatste test is een **regressietest, geen vormtest**: het
`requires_login`-vinkje ontbrak ooit (#629), waardoor die beveiligingsinstelling bij
élke opslag stil omviel — `bool(Form(""))` is False. Een herindeling is precies
wanneer zoiets opnieuw sneuvelt.
"""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_agnostisch


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _formulier(client, admin_headers, slug=None):
    r = client.post("/api/v1/forms", json={
        "title": "Kop", "status": "draft",
        "fields": [{"field_type": "text", "label": "Vraag", "position": 0}],
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    form = r.json()
    if slug:
        csrf = csrf_token_for(make_session_value(SEEDED_ADMIN_EMAIL))
        client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
        resp = client.post(f"/admin/formulieren/{form['id']}/instellingen",
                           data={"title": form["title"], "status": "draft",
                                 "slug": slug},
                           headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200, resp.text[:300]
    return form


def _bouwer(client, form_id) -> str:
    resp = client.get(f"/admin/formulieren/{form_id}")
    assert resp.status_code == 200, resp.text[:200]
    return resp.text


def _instellingenknop(html: str) -> str:
    """De knop die het instellingenpaneel opent.

    Niet op het woord "Bewerken" zoeken: dat staat op deze pagina ook bij elke
    veldkaart. Maar `@click="open = !open"` is óók niet genoeg — de beheerschil
    gebruikt diezelfde toggle voor het mobiele menu (`☰`), en mijn eerste versie van
    deze helper vond dáármee de verkeerde knop. Een botsing, precies de fout die
    deze testreeks elders aanwijst.

    De ondubbelzinnige haak is de INHOUD die `edit_toggle` voor deze state rendert:
    `x-show="!open"` staat alleen op dit paar. De veldkaarten gebruiken `edit`.
    """
    merk = '<span x-show="!open">'
    assert merk in html, "er staat geen bewerktoggle op de state `open`"
    start = html.rindex("<button", 0, html.index(merk))
    return html[start:html.index("</button>", start) + len("</button>")]


# ── 1. Bewerken/Annuleren ──────────────────────────────────────────────────

def test_de_instellingenknop_is_een_bewerktoggle(client, admin_headers):
    form = _formulier(client, admin_headers)
    _login(client)
    knop = _instellingenknop(_bouwer(client, form["id"]))

    assert "Bewerken" in knop, knop
    assert "Annuleren" in knop, "de knop wordt niet Annuleren zodra je bewerkt"
    assert "Instellingen" not in knop, knop


def test_de_oude_knop_is_verdwenen(client, admin_headers):
    """De keerzijde van de test hierboven: zonder haar zou een tweede knop naast de
    toggle ook slagen."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = _bouwer(client, form["id"])
    assert ">Instellingen<" not in html


# ── 2. De links op één regel ───────────────────────────────────────────────

def test_beide_links_staan_op_een_regel(client, admin_headers):
    form = _formulier(client, admin_headers, slug="kopregel")
    _login(client)
    html = _bouwer(client, form["id"])

    start = html.index("Deellink:")
    regel = html[html.rindex("<p", 0, start):html.index("</p>", start)]
    assert "/f/kopregel" in regel, "de leesbare link staat in een eigen blok"
    assert "inzendingen" in regel


def test_zonder_slug_blijft_de_regel_heel(client, admin_headers):
    """Dat is wat stukgaat bij het samenvoegen: een los `·` of een lege span."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = _bouwer(client, form["id"])

    start = html.index("Deellink:")
    regel = html[html.rindex("<p", 0, start):html.index("</p>", start)]
    assert "/f/" not in regel, "er staat een leesbare link zonder slug"
    assert "Leesbare link" not in regel
    assert "inzendingen" in regel


# ── 3. De tekstvakken ──────────────────────────────────────────────────────

@pytest.mark.parametrize("veld_id", ["fbd", "fbc"])
def test_de_tekstvakken_volgen_de_kitstandaard(client, admin_headers, veld_id):
    form = _formulier(client, admin_headers)
    _login(client)
    html = _bouwer(client, form["id"])

    start = html.index(f'id="{veld_id}"')
    tag = html[html.rindex("<textarea", 0, start):html.index(">", start)]
    assert 'rows="4"' in tag, f"{veld_id} wijkt af van de kit: {tag}"


def test_de_sectie_omschrijving_blijft_bewust_korter(client, admin_headers):
    """Geen inconsistentie: de omschrijving van een sectie is een korte toelichting
    boven een groep vragen, geen lopende tekst."""
    r = client.post("/api/v1/forms", json={
        "title": "Met sectie", "status": "draft",
        "sections": [{"title": "Een", "position": 0}],
        "fields": [{"field_type": "text", "label": "V", "position": 0,
                    "section_index": 0}],
    }, headers=admin_headers)
    form = r.json()
    _login(client)
    html = _bouwer(client, form["id"])

    sectie = sorted(form["sections"], key=lambda s: s["position"])[0]
    start = html.index(f'id="sd-{sectie["id"]}"')
    tag = html[html.rindex("<textarea", 0, start):html.index(">", start)]
    assert 'rows="2"' in tag, tag


# ── 4. De volgorde van de velden ───────────────────────────────────────────

def test_de_korte_velden_staan_bij_elkaar(client, admin_headers):
    """Titel · Leesbare link → Status · Max. inzendingen → vinkjes → de tekstvakken."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = _bouwer(client, form["id"])

    plek = {naam: html.index(f'name="{naam}"')
            for naam in ("title", "slug", "status", "max_submissions",
                         "send_confirmation", "description", "confirmation_message")}
    assert plek["title"] < plek["slug"] < plek["status"] < plek["max_submissions"]
    assert plek["max_submissions"] < plek["send_confirmation"]
    assert plek["send_confirmation"] < plek["description"] < plek["confirmation_message"]


def test_het_vinkjesblok_zweeft_niet_meer(client, admin_headers):
    """`pt-5` lijnde uit met een label ernaast; op een eigen regel is dat een gat."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = _bouwer(client, form["id"])

    start = html.index('name="send_confirmation"')
    blok = html[html.rindex("<div", 0, start):start]
    assert "pt-5" not in blok, blok


# ── 5. Regressie: de vier vinkjes ──────────────────────────────────────────

@pytest.mark.parametrize("naam", ["send_confirmation", "allow_edit", "is_anonymous",
                                  "requires_login"])
def test_alle_vier_de_vinkjes_staan_er_nog(client, admin_headers, naam):
    """Geen vormtest maar een regressietest. `requires_login` ontbrak ooit (#629) en
    dan viel die beveiligingsinstelling bij élke opslag stil om, want een niet
    verstuurd vakje leest als False. Een herindeling is precies wanneer dat opnieuw
    gebeurt."""
    form = _formulier(client, admin_headers)
    _login(client)
    assert f'name="{naam}"' in _bouwer(client, form["id"])


def test_opslaan_laat_requires_login_staan(client, admin_headers, db_session):
    """En het gedrag eronder, want de aanwezigheid van een vakje is niet genoeg: het
    moet ook zijn stand meesturen."""
    from app.domains.forms.models import Form

    form = _formulier(client, admin_headers)
    csrf = _login(client)
    client.post(f"/admin/formulieren/{form['id']}/instellingen",
                data={"title": "Kop", "status": "draft", "requires_login": "1"},
                headers={"X-CSRF-Token": csrf})
    db_session.expire_all()
    assert db_session.get(Form, form["id"]).requires_login is True

    # En een tweede opslag zónder het vakje zet hem uit — dát is de bedoelde
    # betekenis van een niet-verstuurd vakje, en het onderscheid met #629.
    client.post(f"/admin/formulieren/{form['id']}/instellingen",
                data={"title": "Kop", "status": "draft"},
                headers={"X-CSRF-Token": csrf})
    db_session.expire_all()
    assert db_session.get(Form, form["id"]).requires_login is False
