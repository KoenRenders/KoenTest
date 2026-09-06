"""#700 + #701 — het vraagtype wijzigen, en één volledige vorm voor beide paden.

Twee helften van hetzelfde probleem. De bouwer had **twee halve formulieren**:
toevoegen kende wél het type maar geen verplicht/hulptekst/min-max, bewerken die wél
maar geen type — precies omgekeerd op het enige veld dat ze deelden. Eén gedeelde
macro lost beide op; het type twee keer inbouwen zou de splitsing bestendigd hebben.

**De blokkade (beslissing Koen):** wijzigen mag zolang er geen inzendingen zijn.
Daarna staat de lijst er wél, maar uitgeschakeld met de reden erbij (§2.12) —
strenger dan v1.14, en bewust: bewaarde antwoorden verwijzen naar hun veld, en een
typewissel maakt ze niet fout maar betekenisloos.

**Bij een typewissel: opties bewaren, sprongregels wissen.** Terugzetten hoort niets
te kosten, maar een optie met een `skip_to_section` onder een niet-vertakbare vraag
is een slapende vertakking die weer opleeft zodra iemand het type terugzet — het
onzichtbare soort schade, net als bij #692.
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


def _formulier(client, admin_headers, velden=None):
    r = client.post("/api/v1/forms", json={
        "title": "Types", "status": "open", "is_anonymous": True,
        "sections": [{"title": "Een", "position": 0},
                     {"title": "Twee", "position": 1}],
        "fields": velden if velden is not None else [
            {"field_type": "text", "label": "Vraag", "position": 0,
             "section_index": 0}],
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _bewerk(client, csrf, form, veld_id, **velden):
    data = {"label": "Vraag"}
    data.update(velden)
    return client.post(f"/admin/formulieren/{form['id']}/velden/{veld_id}",
                       data=data, headers={"X-CSRF-Token": csrf})


def _lees(client, admin_headers, form_id):
    return client.get(f"/api/v1/forms/{form_id}", headers=admin_headers).json()


# ── 1. Het type kan gewijzigd worden ───────────────────────────────────────

def test_een_tekstvraag_wordt_een_meerkeuzevraag(client, admin_headers):
    """Voorheen: verwijderen en opnieuw maken — plaats kwijt, opties kwijt."""
    form = _formulier(client, admin_headers)
    csrf = _login(client)
    veld = form["fields"][0]

    assert _bewerk(client, csrf, form, veld["id"],
                   field_type="radio").status_code == 200

    na = _lees(client, admin_headers, form["id"])
    assert na["fields"][0]["field_type"] == "radio"
    assert na["fields"][0]["id"] == veld["id"], "het veld is vervangen i.p.v. gewijzigd"


def test_de_plaats_blijft_bij_een_typewissel(client, admin_headers):
    form = _formulier(client, admin_headers, [
        {"field_type": "text", "label": "Eerst", "position": 0, "section_index": 0},
        {"field_type": "text", "label": "Vraag", "position": 1, "section_index": 0},
    ])
    csrf = _login(client)
    tweede = next(f for f in form["fields"] if f["label"] == "Vraag")

    _bewerk(client, csrf, form, tweede["id"], field_type="number")

    na = _lees(client, admin_headers, form["id"])
    gewijzigd = next(f for f in na["fields"] if f["label"] == "Vraag")
    assert gewijzigd["position"] == 1 and gewijzigd["section_id"] == tweede["section_id"]


def test_een_ongeldig_type_wordt_geweigerd(client, admin_headers):
    form = _formulier(client, admin_headers)
    csrf = _login(client)

    resp = _bewerk(client, csrf, form, form["fields"][0]["id"],
                   field_type="bestaat-niet")
    assert resp.status_code == 422, resp.text[:200]


# ── 2. Opties bewaren, sprongregels wissen ─────────────────────────────────

def test_opties_blijven_bij_een_typewissel(client, admin_headers):
    """Terugzetten hoort niets te kosten."""
    form = _formulier(client, admin_headers, [
        {"field_type": "radio", "label": "Vraag", "position": 0, "section_index": 0,
         "options": [{"label": "A", "position": 0}, {"label": "B", "position": 1}]},
    ])
    csrf = _login(client)
    veld = form["fields"][0]

    _bewerk(client, csrf, form, veld["id"], field_type="text")

    na = _lees(client, admin_headers, form["id"])
    labels = sorted(o["label"] for o in na["fields"][0]["options"])
    assert labels == ["A", "B"], "de opties zijn weg"


def test_een_sprongregel_verdwijnt_bij_een_niet_vertakbaar_type(client,
                                                                admin_headers):
    """De onzichtbare helft. Een optie met een `skip_to_section` onder een vraag die
    niet kan vertakken, is een slapende vertakking die weer opleeft zodra iemand het
    type terugzet."""
    form = _formulier(client, admin_headers, [
        {"field_type": "radio", "label": "Vraag", "position": 0, "section_index": 0,
         "options": [{"label": "A", "position": 0, "skip_to_section_index": 1},
                     {"label": "B", "position": 1, "skip_to_end": True}]},
    ])
    csrf = _login(client)
    veld = form["fields"][0]
    voor = {o["label"]: o for o in _lees(client, admin_headers,
                                        form["id"])["fields"][0]["options"]}
    assert voor["A"]["skip_to_section_id"] is not None, "opzet klopt niet"

    _bewerk(client, csrf, form, veld["id"], field_type="checkbox")

    na = {o["label"]: o for o in _lees(client, admin_headers,
                                      form["id"])["fields"][0]["options"]}
    assert na["A"]["skip_to_section_id"] is None, "de slapende vertakking staat er nog"
    assert na["B"]["skip_to_end"] is False
    assert set(na) == {"A", "B"}, "de opties zijn wél verdwenen"


def test_een_vertakbaar_type_houdt_zijn_sprongen(client, admin_headers):
    """De keerzijde: van radio naar select mag niets wissen — allebei vertakbaar."""
    form = _formulier(client, admin_headers, [
        {"field_type": "radio", "label": "Vraag", "position": 0, "section_index": 0,
         "options": [{"label": "A", "position": 0, "skip_to_section_index": 1}]},
    ])
    csrf = _login(client)

    _bewerk(client, csrf, form, form["fields"][0]["id"], field_type="select")

    na = _lees(client, admin_headers, form["id"])["fields"][0]
    assert na["field_type"] == "select"
    assert na["options"][0]["skip_to_section_id"] is not None, "de sprong is gewist"


# ── 3. De blokkade bij inzendingen ─────────────────────────────────────────

def _dien_in(client, form):
    veld = form["fields"][0]
    resp = client.post(f"/formulier/{form['share_token']}",
                       data={f"f{veld['id']}": "iets"})
    assert resp.status_code == 200, resp.text[:200]


def test_met_inzendingen_kan_het_type_niet_meer(client, admin_headers):
    form = _formulier(client, admin_headers)
    _dien_in(client, form)
    csrf = _login(client)

    resp = _bewerk(client, csrf, form, form["fields"][0]["id"], field_type="radio")
    assert resp.status_code == 422, resp.text[:200]

    na = _lees(client, admin_headers, form["id"])
    assert na["fields"][0]["field_type"] == "text", "het type is tóch gewijzigd"


def test_met_inzendingen_blijft_de_rest_wel_bewerkbaar(client, admin_headers):
    """De blokkade geldt het type, niet het veld. Zonder deze grens zou een
    formulier met inzendingen helemaal bevroren zijn."""
    form = _formulier(client, admin_headers)
    _dien_in(client, form)
    csrf = _login(client)

    resp = _bewerk(client, csrf, form, form["fields"][0]["id"],
                   help_text="Nieuwe uitleg")
    assert resp.status_code == 200, resp.text[:200]
    assert _lees(client, admin_headers,
                 form["id"])["fields"][0]["help_text"] == "Nieuwe uitleg"


def test_het_scherm_toont_de_lijst_uitgeschakeld_met_de_reden(client, admin_headers):
    """§2.12: tonen maar disabled met de reden, niet verbergen. Een keuze die er niet
    staat, laat je zoeken."""
    form = _formulier(client, admin_headers)
    _dien_in(client, form)
    _login(client)

    html = client.get(f"/admin/formulieren/{form['id']}").text
    start = html.index('name="field_type"')
    select = html[html.rindex("<select", 0, start):html.index(">", start)]
    assert "disabled" in select, select
    assert "inzendingen" in select, "de reden ontbreekt in de tooltip"


def test_zonder_inzendingen_staat_de_lijst_gewoon_aan(client, admin_headers):
    form = _formulier(client, admin_headers)
    _login(client)

    html = client.get(f"/admin/formulieren/{form['id']}").text
    start = html.index('name="field_type"')
    select = html[html.rindex("<select", 0, start):html.index(">", start)]
    assert "disabled" not in select, select


# ── 4. Eén vorm voor beide paden (#701) ────────────────────────────────────

def test_toevoegen_kent_dezelfde_velden_als_bewerken(client, admin_headers):
    """De kern van #701: de twee halve formulieren zijn er één geworden."""
    form = _formulier(client, admin_headers)
    _login(client)
    html = client.get(f"/admin/formulieren/{form['id']}").text

    # De toevoegvorm is te herkennen aan het id-achtervoegsel "nieuw".
    start = html.index('id="fl-nieuw"')
    vorm = html[html.rindex("<form", 0, start):html.index("</form>", start)]
    for veld in ('name="label"', 'name="field_type"', 'name="help_text"',
                 'name="required"'):
        assert veld in vorm, f"{veld} ontbreekt in de toevoegvorm"


def test_een_nieuwe_vraag_wordt_ineens_volledig_bewaard(client, admin_headers):
    form = _formulier(client, admin_headers)
    csrf = _login(client)
    sectie = sorted(form["sections"], key=lambda s: s["position"])[0]

    resp = client.post(f"/admin/formulieren/{form['id']}/velden",
                       data={"label": "Nieuwe vraag", "field_type": "number",
                             "section_id": str(sectie["id"]),
                             "help_text": "Uitleg", "required": "1",
                             "min_value": "3"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200, resp.text[:300]

    na = _lees(client, admin_headers, form["id"])
    nieuw = next(f for f in na["fields"] if f["label"] == "Nieuwe vraag")
    assert nieuw["field_type"] == "number"
    assert nieuw["help_text"] == "Uitleg" and nieuw["required"] is True
    assert str(nieuw["min_value"]).startswith("3")


def test_de_lege_kaart_maakt_nog_geen_veld_aan(client, admin_headers, db_session):
    """Test 1 uit het issue, en op de DATABANK getoetst.

    De verleidelijke aanpak — bij de klik meteen een veld aanmaken en in bewerkmodus
    openen — zou een tijdelijke naam als "Nieuwe vraag" wegschrijven, en wie afbreekt
    houdt een echte vraag met die naam over. Een test op het scherm zou ook groen
    staan bij díe oplossing; deze niet.
    """
    from app.domains.forms.models import FormField

    form = _formulier(client, admin_headers)
    _login(client)
    voor = db_session.query(FormField).filter(
        FormField.form_id == form["id"]).count()

    client.get(f"/admin/formulieren/{form['id']}")

    db_session.expire_all()
    assert db_session.query(FormField).filter(
        FormField.form_id == form["id"]).count() == voor, (
        "het openen van de bouwer maakte al een veld aan")
    assert not db_session.query(FormField).filter(
        FormField.label == "Nieuwe vraag").all()
