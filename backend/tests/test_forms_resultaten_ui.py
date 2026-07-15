"""Formulieren-admin: resultaten-tab (geaggregeerde statistiek) + JSON-export
(#454). De aggregatie zelf komt uit compute_results; hier testen we dat de
admin-UI-routes ze correct ontsluiten (auth, telling, gemiddelde, JSON-vorm)."""
import json

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.test_forms import _create_form, _field_id, _option_id


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _submit(client, form, *, checkbox_opt, rating):
    body = {
        "submitter_name": "Jan", "submitter_email": "jan@example.com",
        "answers": [
            {"field_id": _field_id(form, "Email"), "text": "jan@example.com"},
            {"field_id": _field_id(form, "Naam"), "text": "Jan"},
            {"field_id": _field_id(form, "Zaterdag namiddag"),
             "option_ids": [_option_id(form, "Zaterdag namiddag", checkbox_opt)]},
            {"field_id": _field_id(form, "Tevredenheid"), "rating": rating},
        ],
    }
    r = client.post(f"/api/v1/forms/by-token/{form['share_token']}/submit", json=body)
    assert r.status_code == 200, r.text


def test_resultaten_requires_session(client, admin_headers):
    form = _create_form(client, admin_headers)
    assert client.get(f"/admin/formulieren/{form['id']}/resultaten").status_code == 401


def test_resultaten_toont_tellingen_en_gemiddelde(client, admin_headers):
    form = _create_form(client, admin_headers)
    _submit(client, form, checkbox_opt="BBQ bakken", rating=4)
    _submit(client, form, checkbox_opt="BBQ bakken", rating=2)
    _login(client)

    r = client.get(f"/admin/formulieren/{form['id']}/resultaten")
    assert r.status_code == 200
    assert "2 " in r.text and "inzendingen" in r.text
    assert "BBQ bakken" in r.text
    # Rating-gemiddelde (4 en 2) = 3.0
    assert "Gemiddelde" in r.text and "3.0" in r.text


def test_json_export_levert_definitie(client, admin_headers):
    form = _create_form(client, admin_headers)
    _login(client)
    r = client.get(f"/admin/formulieren/{form['id']}/json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "attachment" in r.headers.get("content-disposition", "")
    data = json.loads(r.text)
    assert data["title"] == form["title"]
    labels = [f["label"] for f in data["fields"]]
    assert "Zaterdag namiddag" in labels and "Tevredenheid" in labels
