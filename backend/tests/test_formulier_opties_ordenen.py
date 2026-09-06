"""#697 — keuzeopties konden niet geordend worden.

Secties en velden hebben ↑↓, de opties binnen een keuzevraag niet. Een optie
verplaatsen betekende dus: verwijderen en opnieuw toevoegen — en dan verlies je
haar `skip_to_section` én haar id, en daarmee de koppeling met alles wat er al naar
verwijst.

Twee dingen waar dit stil kan misgaan, en waarvoor de tests hieronder bestaan:

- **De broers-en-zussen-afbakening.** Opties van dít veld, niet van het formulier.
  Een fout daarin blijft onopgemerkt zolang er één keuzeveld is en wisselt meteen
  opties tussen twee vragen zodra er twee zijn.
- **De sprongregel.** Verplaatsen mag branching niet stilzwijgend verleggen. Dat is
  hetzelfde soort onzichtbare schade als bij #692: de volgorde oogt goed terwijl de
  wizard ergens anders heen loopt.

Beslissing van Koen: **"Anders" krijgt geen bijzondere behandeling** en mag dus ook
in het midden staan. Geen onzichtbare regel die haar achteraan duwt.
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


def _formulier(client, admin_headers, velden):
    r = client.post("/api/v1/forms",
                    json={"title": "Ordenen", "status": "draft", "fields": velden},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _keuzeveld(label, opties, section_index=None, positie=0):
    veld = {"field_type": "radio", "label": label, "position": positie,
            "options": [{"label": o, "position": i} for i, o in enumerate(opties)]}
    if section_index is not None:
        veld["section_index"] = section_index
    return veld


def _verplaats(client, csrf, form_id, option_id, richting):
    return client.post(
        f"/admin/formulieren/{form_id}/opties/{option_id}/verplaats",
        data={"richting": richting}, headers={"X-CSRF-Token": csrf})


def _labels(client, admin_headers, form_id, veld_label):
    na = client.get(f"/api/v1/forms/{form_id}", headers=admin_headers).json()
    veld = next(f for f in na["fields"] if f["label"] == veld_label)
    return [o["label"] for o in sorted(veld["options"],
                                       key=lambda o: (o["position"], o["id"]))]


# ── 1. Verplaatsen werkt ────────────────────────────────────────────────────

def test_een_optie_gaat_omhoog(client, admin_headers):
    form = _formulier(client, admin_headers,
                      [_keuzeveld("Kies", ["Een", "Twee", "Drie"])])
    csrf = _login(client)
    veld = form["fields"][0]
    twee = next(o for o in veld["options"] if o["label"] == "Twee")

    assert _verplaats(client, csrf, form["id"], twee["id"], "op").status_code == 200
    assert _labels(client, admin_headers, form["id"], "Kies") == ["Twee", "Een", "Drie"]


def test_een_optie_gaat_omlaag(client, admin_headers):
    form = _formulier(client, admin_headers,
                      [_keuzeveld("Kies", ["Een", "Twee", "Drie"])])
    csrf = _login(client)
    veld = form["fields"][0]
    een = next(o for o in veld["options"] if o["label"] == "Een")

    assert _verplaats(client, csrf, form["id"], een["id"], "neer").status_code == 200
    assert _labels(client, admin_headers, form["id"], "Kies") == ["Twee", "Een", "Drie"]


def test_buiten_bereik_is_een_no_op_en_geen_fout(client, admin_headers):
    """De bovenste omhoog. De knop staat op `disabled`, maar een herhaalde POST of
    een oud tabblad hoort hier geen fout te geven."""
    form = _formulier(client, admin_headers, [_keuzeveld("Kies", ["Een", "Twee"])])
    csrf = _login(client)
    een = next(o for o in form["fields"][0]["options"] if o["label"] == "Een")

    assert _verplaats(client, csrf, form["id"], een["id"], "op").status_code == 200
    assert _labels(client, admin_headers, form["id"], "Kies") == ["Een", "Twee"]


# ── 2. Alleen binnen het eigen veld ─────────────────────────────────────────

def test_opties_wisselen_niet_met_die_van_een_ander_veld(client, admin_headers):
    """Test 3 uit het issue: twee keuzevelden naast elkaar.

    Zonder de filter op het eigen veld zou de onderste optie van vraag A van plaats
    wisselen met de bovenste van vraag B — en dat merk je niet zolang er één
    keuzeveld op het formulier staat.
    """
    form = _formulier(client, admin_headers, [
        _keuzeveld("Vraag A", ["A1", "A2"], positie=0),
        _keuzeveld("Vraag B", ["B1", "B2"], positie=1),
    ])
    csrf = _login(client)
    veld_a = next(f for f in form["fields"] if f["label"] == "Vraag A")
    a2 = next(o for o in veld_a["options"] if o["label"] == "A2")

    assert _verplaats(client, csrf, form["id"], a2["id"], "op").status_code == 200

    assert _labels(client, admin_headers, form["id"], "Vraag A") == ["A2", "A1"]
    assert _labels(client, admin_headers, form["id"], "Vraag B") == ["B1", "B2"], (
        "de opties van het andere veld zijn meeverschoven")


def test_de_onderste_optie_zakt_niet_naar_het_volgende_veld(client, admin_headers):
    """De spiegel van de test hierboven, en de kant waar een ontbrekende filter het
    hardst zou opvallen."""
    form = _formulier(client, admin_headers, [
        _keuzeveld("Vraag A", ["A1", "A2"], positie=0),
        _keuzeveld("Vraag B", ["B1", "B2"], positie=1),
    ])
    csrf = _login(client)
    veld_a = next(f for f in form["fields"] if f["label"] == "Vraag A")
    a2 = next(o for o in veld_a["options"] if o["label"] == "A2")

    assert _verplaats(client, csrf, form["id"], a2["id"], "neer").status_code == 200
    assert _labels(client, admin_headers, form["id"], "Vraag A") == ["A1", "A2"]
    assert _labels(client, admin_headers, form["id"], "Vraag B") == ["B1", "B2"]


# ── 3. De sprongregel verhuist mee ──────────────────────────────────────────

def test_de_sprong_blijft_aan_dezelfde_optie_hangen(client, admin_headers):
    """Test 4 uit het issue. Verplaatsen mag branching niet stilzwijgend verleggen.

    De volgorde oogt na afloop goed; of de sprong nog bij de juiste optie hoort,
    zie je alleen door ernaar te vragen — hetzelfde soort onzichtbare schade als in
    #692.
    """
    r = client.post("/api/v1/forms", json={
        "title": "Sprong", "status": "draft",
        "sections": [{"title": "Een", "position": 0},
                     {"title": "Twee", "position": 1},
                     {"title": "Drie", "position": 2}],
        "fields": [{"field_type": "radio", "label": "Kies", "position": 0,
                    "section_index": 0,
                    "options": [{"label": "Gewoon", "position": 0},
                                {"label": "Springt", "position": 1,
                                 "skip_to_section_index": 2},
                                {"label": "Einde", "position": 2,
                                 "skip_to_end": True}]}],
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    form = r.json()
    csrf = _login(client)
    springt = next(o for o in form["fields"][0]["options"] if o["label"] == "Springt")
    derde = sorted(form["sections"], key=lambda s: s["position"])[2]

    assert _verplaats(client, csrf, form["id"], springt["id"], "op").status_code == 200

    assert _labels(client, admin_headers, form["id"], "Kies") == [
        "Springt", "Gewoon", "Einde"]
    na = client.get(f"/api/v1/forms/{form['id']}", headers=admin_headers).json()
    per_label = {o["label"]: o for o in na["fields"][0]["options"]}
    assert per_label["Springt"]["skip_to_section_id"] == derde["id"], (
        "de sprong is van optie verwisseld")
    assert per_label["Einde"]["skip_to_end"] is True
    assert per_label["Gewoon"]["skip_to_section_id"] is None


def test_de_id_van_een_optie_blijft_bestaan(client, admin_headers):
    """Waarom verplaatsen bestaat: verwijderen-en-opnieuw-toevoegen gaf een nieuwe
    id, en daarmee verdwijnt de koppeling met alles wat ernaar verwijst."""
    form = _formulier(client, admin_headers, [_keuzeveld("Kies", ["Een", "Twee"])])
    csrf = _login(client)
    twee = next(o for o in form["fields"][0]["options"] if o["label"] == "Twee")

    _verplaats(client, csrf, form["id"], twee["id"], "op")

    na = client.get(f"/api/v1/forms/{form['id']}", headers=admin_headers).json()
    assert twee["id"] in {o["id"] for o in na["fields"][0]["options"]}


# ── 4. "Anders" is een gewone optie ─────────────────────────────────────────

def test_anders_mag_ook_in_het_midden_staan(client, admin_headers):
    """Beslissing Koen: geen bijzondere behandeling, dus ook geen onzichtbare regel
    die haar achteraan duwt of de ↑-knop laat weigeren."""
    r = client.post("/api/v1/forms", json={
        "title": "Anders", "status": "draft",
        "fields": [{"field_type": "radio", "label": "Kies", "position": 0,
                    "options": [{"label": "Een", "position": 0},
                                {"label": "Twee", "position": 1},
                                {"label": "Andere", "position": 2,
                                 "is_other": True}]}],
    }, headers=admin_headers)
    form = r.json()
    csrf = _login(client)
    anders = next(o for o in form["fields"][0]["options"] if o["is_other"])

    assert _verplaats(client, csrf, form["id"], anders["id"], "op").status_code == 200
    assert _labels(client, admin_headers, form["id"], "Kies") == [
        "Een", "Andere", "Twee"]

    na = client.get(f"/api/v1/forms/{form['id']}", headers=admin_headers).json()
    per_label = {o["label"]: o for o in na["fields"][0]["options"]}
    assert per_label["Andere"]["is_other"] is True, "de vlag is meeverhuisd"


# ── 5. Het scherm ───────────────────────────────────────────────────────────

def test_de_optierij_toont_de_verplaatsknoppen(client, admin_headers):
    form = _formulier(client, admin_headers,
                      [_keuzeveld("Kies", ["Een", "Twee", "Drie"])])
    _login(client)
    opties = form["fields"][0]["options"]

    html = client.get(f"/admin/formulieren/{form['id']}").text
    for o in opties:
        assert f'/opties/{o["id"]}/verplaats' in html, (
            f"optie {o['label']} heeft geen verplaatsknop")


def test_de_sortering_komt_uit_de_relatie_en_niet_uit_de_template(client,
                                                                  admin_headers):
    """Een bronregel: de relatie sorteert al op `position` (`models.py`). Een tweede
    sorteerplek in het sjabloon loopt vroeg of laat uiteen met de eerste, en dan
    toont het scherm iets anders dan wat er staat."""
    bron = open("app/domains/forms/templates/_fb_builder.html",
                encoding="utf-8").read()
    start = bron.index("{% for o in f.options %}")
    assert "sort(" not in bron[start:start + 200], (
        "het sjabloon sorteert de opties zelf")
