"""#692 — een JSON-export van een formulier importeert niet terug.

Exporteur en importeur spraken een andere taal. De import verwijst naar secties met
hun **index in de payload**; de export schreef **databank-id's**: `section_index`
tegenover `section_id`, `next_section_index` tegenover `next_section_id`,
`skip_to_section_index` tegenover `skip_to_section_id`. De invoerschema's negeren
onbekende sleutels, dus `section_id` verdween, `section_index` viel terug op None,
en elk veld belandde bij géén sectie: lege secties bovenaan, alle vragen los
eronder.

**Let op wat je niet ziet.** De zichtbare schade is de indeling. Onzichtbaar
verdwenen óók de sectie- en optiesprongen. Repareer je alleen de indeling, dan oogt
het formulier normaal terwijl de wizard lineair door secties loopt die overgeslagen
hadden moeten worden. De rondrit-test hieronder is er precies voor die tweede helft.

Niet nieuw: `next_section_id` bestaat sinds branching landde (#336). De rondrit
heeft nooit gewerkt voor een formulier met secties — er had alleen nog niemand een
export teruggeladen.
"""
import json

import pytest

from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_agnostisch


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _payload_met_sprongen():
    """Drie secties, met een sectiesprong én een optiesprong.

    Sectie 0 springt naar sectie 2 (slaat 1 over); de optie "Meteen klaar" springt
    naar het einde. Beide zijn onzichtbaar in de indeling en zichtbaar in de wizard.
    """
    return {
        "title": "Rondrit", "status": "open", "is_anonymous": True,
        "description": "Met sprongen",
        "send_confirmation": True, "allow_edit": True,
        "confirmation_message": "Bedankt!",
        "sections": [
            {"title": "Een", "position": 0, "next_section_index": 2},
            {"title": "Twee", "position": 1},
            {"title": "Drie", "position": 2, "next_is_end": True},
        ],
        "fields": [
            {"field_type": "radio", "label": "Kies", "position": 0,
             "section_index": 0,
             "options": [{"label": "Verder", "position": 0},
                         {"label": "Meteen klaar", "position": 1,
                          "skip_to_end": True},
                         {"label": "Naar drie", "position": 2,
                          "skip_to_section_index": 2}]},
            {"field_type": "text", "label": "Vraag twee", "position": 1,
             "section_index": 1},
            {"field_type": "text", "label": "Vraag drie", "position": 2,
             "section_index": 2},
        ],
    }


def _maak(client, admin_headers, payload=None):
    r = client.post("/api/v1/forms", json=payload or _payload_met_sprongen(),
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _download(client, form_id: int) -> dict:
    resp = client.get(f"/admin/formulieren/{form_id}/json")
    assert resp.status_code == 200, resp.text
    return json.loads(resp.content)


def _importeer(client, csrf, form_id: int, definitie: dict):
    return client.post(f"/admin/formulieren/{form_id}/json-import",
                       data={"payload": json.dumps(definitie)},
                       headers={"X-CSRF-Token": csrf})


# ── 1. De export spreekt de taal van de import ──────────────────────────────

def test_de_export_gebruikt_indexen_en_geen_ids(client, admin_headers):
    bron = _maak(client, admin_headers)
    _login(client)
    definitie = _download(client, bron["id"])

    tekst = json.dumps(definitie)
    for sleutel in ("section_id", "next_section_id", "skip_to_section_id",
                    '"id"', "share_token", "submission_count"):
        assert sleutel not in tekst, f"{sleutel} hoort niet in een export"
    assert definitie["fields"][0]["section_index"] == 0
    assert definitie["sections"][0]["next_section_index"] == 2


# ── 2. De rondrit, inclusief de onzichtbare helft ───────────────────────────

def test_de_rondrit_behoudt_de_indeling(client, admin_headers):
    bron = _maak(client, admin_headers)
    doel = _maak(client, admin_headers, {"title": "Leeg", "status": "draft",
                                         "fields": []})
    csrf = _login(client)

    assert _importeer(client, csrf, doel["id"], _download(client, bron["id"])
                      ).status_code == 200

    na = client.get(f"/api/v1/forms/{doel['id']}", headers=admin_headers).json()
    assert len(na["sections"]) == 3
    per_index = {s["title"]: s["id"] for s in na["sections"]}
    for veld, sectie in (("Kies", "Een"), ("Vraag twee", "Twee"),
                         ("Vraag drie", "Drie")):
        f = next(f for f in na["fields"] if f["label"] == veld)
        assert f["section_id"] == per_index[sectie], (
            f"{veld} hangt niet aan sectie {sectie}")


def test_de_rondrit_behoudt_de_sprongen(client, admin_headers):
    """De helft die je niet ziet. Zonder deze test oogt het formulier normaal
    terwijl de wizard lineair door secties loopt die overgeslagen hadden moeten
    worden."""
    bron = _maak(client, admin_headers)
    doel = _maak(client, admin_headers, {"title": "Leeg", "status": "draft",
                                         "fields": []})
    csrf = _login(client)
    assert _importeer(client, csrf, doel["id"], _download(client, bron["id"])
                      ).status_code == 200

    na = client.get(f"/api/v1/forms/{doel['id']}", headers=admin_headers).json()
    secties = sorted(na["sections"], key=lambda s: s["position"])
    assert secties[0]["next_section_id"] == secties[2]["id"], "de sectiesprong is weg"
    assert secties[2]["next_is_end"] is True

    opties = next(f for f in na["fields"] if f["label"] == "Kies")["options"]
    per_label = {o["label"]: o for o in opties}
    assert per_label["Meteen klaar"]["skip_to_end"] is True
    assert per_label["Naar drie"]["skip_to_section_id"] == secties[2]["id"], (
        "de optiesprong is weg")


def test_de_rondrit_behoudt_de_instellingen(client, admin_headers):
    """#635-3 voegde deze juist aan de import toe; ze mogen niet sneuvelen bij het
    opschonen van de export."""
    bron = _maak(client, admin_headers)
    doel = _maak(client, admin_headers, {"title": "Leeg", "status": "draft",
                                         "fields": []})
    csrf = _login(client)
    assert _importeer(client, csrf, doel["id"], _download(client, bron["id"])
                      ).status_code == 200

    na = client.get(f"/api/v1/forms/{doel['id']}", headers=admin_headers).json()
    assert na["title"] == "Rondrit"
    assert na["description"] == "Met sprongen"
    assert na["status"] == "open"
    assert na["is_anonymous"] is True
    assert na["send_confirmation"] is True
    assert na["allow_edit"] is True
    assert na["confirmation_message"] == "Bedankt!"


# ── 3. De oude vorm wordt geweigerd, niet vertaald ──────────────────────────

@pytest.mark.parametrize("sleutel", ["section_id", "next_section_id",
                                     "skip_to_section_id"])
def test_een_bestand_in_de_id_vorm_wordt_geweigerd(client, admin_headers, sleutel):
    """Weigeren en niet vertalen: er staan geen id-bestanden in het veld, en een
    vertaallaag zou een dialect onderhouden dat niemand meer produceert.

    De melding moet er zijn — zonder haar zou zo'n bestand stilzwijgend als "alle
    velden zonder sectie" binnenkomen, wat precies de gemelde schade is.
    """
    doel = _maak(client, admin_headers, {"title": "Leeg", "status": "draft",
                                         "fields": []})
    csrf = _login(client)

    resp = _importeer(client, csrf, doel["id"], {
        "title": "Oud", "sections": [{"title": "Een", "position": 0}],
        "fields": [{"field_type": "text", "label": "V", "position": 0,
                    sleutel: 1}]})
    assert resp.status_code == 200, resp.text
    assert "oudere export" in resp.text, resp.text[:400]


def test_een_handgeschreven_bestand_zonder_ids_werkt_gewoon(client, admin_headers):
    """De keerzijde, en niet theoretisch: Koens bestand van een maand geleden is met
    de hand in de import-woordenschat geschreven. Zou de weigering te breed zijn,
    dan brak dat."""
    doel = _maak(client, admin_headers, {"title": "Leeg", "status": "draft",
                                         "fields": []})
    csrf = _login(client)

    resp = _importeer(client, csrf, doel["id"], _payload_met_sprongen())
    assert resp.status_code == 200, resp.text
    assert "oudere export" not in resp.text

    na = client.get(f"/api/v1/forms/{doel['id']}", headers=admin_headers).json()
    assert len(na["sections"]) == 3 and len(na["fields"]) == 3


def test_de_json_api_aanvaardt_nog_altijd_extra_sleutels(client, admin_headers):
    """De weigering is een gerichte controle op drie sleutels, geen
    `extra="forbid"` op de schema's: die bedienen óók `POST /forms`, en daar zou
    elke extra sleutel plots een 422 geven. Een reparatie van de import hoort de API
    niet te breken."""
    r = client.post("/api/v1/forms",
                    json={"title": "Met extra", "status": "draft", "fields": [],
                          "iets_onbekends": True},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
