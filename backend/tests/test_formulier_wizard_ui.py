"""Publieke formulier-wizard (#454): een meersectie-formulier wordt stap-per-stap
getoond met branching. De server bouwt het stapmodel (branching → stap-indices);
de client (Alpine) volgt het. Bij één sectie of losse velden: geen wizard.
"""


def _create(client, admin_headers, payload):
    r = client.post("/api/v1/forms", json=payload, headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _multi_section_payload():
    return {
        "title": "Wizard test", "status": "open", "is_anonymous": True,
        "sections": [
            {"title": "Stap 1", "position": 0, "next_is_end": False},
            {"title": "Stap 2", "position": 1, "next_is_end": True},
        ],
        "fields": [
            {"field_type": "radio", "label": "Kies", "position": 0, "section_index": 0,
             "options": [
                 {"label": "Verder", "position": 0},
                 {"label": "Meteen klaar", "position": 1, "skip_to_end": True},
             ]},
            {"field_type": "text", "label": "Naam2", "required": True,
             "position": 1, "section_index": 1},
        ],
    }


def test_wizard_renders_for_multi_section(client, admin_headers):
    form = _create(client, admin_headers, _multi_section_payload())
    html = client.get(f"/formulier/{form['share_token']}").text
    assert "formWizard(" in html
    assert 'data-step="0"' in html and 'data-step="1"' in html
    assert "Volgende" in html
    # Branching is in het stapmodel gebakken (een optie met een skip-doel).
    assert '"skips"' in html and '"opt"' in html
    assert '"end": true' in html  # next_is_end op sectie 2 + skip_to_end


def test_wizard_drops_native_required_on_section_fields(client, admin_headers):
    form = _create(client, admin_headers, _multi_section_payload())
    html = client.get(f"/formulier/{form['share_token']}").text
    # Het verplichte tekstveld in sectie 2 mag in wizard-modus geen native
    # 'required' hebben (anders blokkeert een verborgen veld de submit); de server
    # valideert de bereikte route. We vinden de input en checken het attribuut niet.
    field_id = next(f["id"] for f in form["fields"] if f["label"] == "Naam2")
    marker = f'name="f{field_id}"'
    assert marker in html
    snippet = html[html.index(marker): html.index(marker) + 200]
    assert "required" not in snippet


def test_no_wizard_for_single_section(client, admin_headers):
    payload = {
        "title": "Enkele sectie", "status": "open", "is_anonymous": True,
        "sections": [{"title": "Alles", "position": 0, "next_is_end": True}],
        "fields": [{"field_type": "text", "label": "Naam", "required": True,
                    "position": 0, "section_index": 0}],
    }
    form = _create(client, admin_headers, payload)
    html = client.get(f"/formulier/{form['share_token']}").text
    assert "formWizard(" not in html
    # Zonder wizard behoudt het enige veld zijn native required.
    field_id = form["fields"][0]["id"]
    marker = f'name="f{field_id}"'
    snippet = html[html.index(marker): html.index(marker) + 200]
    assert "required" in snippet
