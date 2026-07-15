"""#479: de ODS-export-knop in de formulieren-admin gaf een 422 JSON
('Ongeldig formaat (enkel ods)') i.p.v. een ODS-bestand. Oorzaak: de admin-route
riep export_form() direct aan zonder format, en die default is een FastAPI
Query-object (niet de string 'ods') → de format-check faalde. Regressie: de
admin-export levert een echt ODS-bestand."""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.test_forms import _create_form, _field_id


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_admin_ods_export_returns_ods_not_json_error(client, admin_headers):
    form = _create_form(client, admin_headers)
    # één inzending zodat er iets te exporteren valt
    client.post(f"/api/v1/forms/by-token/{form['share_token']}/submit", json={
        "submitter_name": "An", "submitter_email": "an@example.com",
        "answers": [
            {"field_id": _field_id(form, "Email"), "text": "an@example.com"},
            {"field_id": _field_id(form, "Naam"), "text": "An"},
        ]})
    _login(client)

    resp = client.get(f"/admin/formulieren/{form['id']}/export")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith(
        "application/vnd.oasis.opendocument.spreadsheet")
    assert "attachment" in resp.headers.get("content-disposition", "")
    # Een ODS is een zip → begint met PK; zeker geen JSON-foutmelding.
    assert resp.content[:2] == b"PK"
    assert b"Ongeldig formaat" not in resp.content
