"""#724 — na een 422 opent de wizard op de stap van het gemelde veld.

De foutweg rendert `formulier.html` opnieuw met een banner die het veld bij naam
noemt. De ingevulde antwoorden overleven dat, maar de wizard begon opnieuw bij stap
0 omdat Alpine het component vers initialiseert. Je kreeg dus een melding over een
vraag die je niet ziet, op een stap waar je niet was.

**Dit is het enige deel van #724 dat een servertest kan aantonen.** De stapcontrole
zelf gebeurt in de browser en staat in `tests_e2e/test_formulier_wizard_stap.py`.

De tweede test is de tegenproef die het issue expliciet vraagt: een post die de
stapcontrole omzeilt moet nog steeds een 422 opleveren. Zonder haar zou "de client
valideert nu" ook groen zijn wanneer de server het opgegeven had.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (lokaal):
  * `fout.veld_id = field.id` uit `_fail` gehaald → de eerste test valt om, de
    wizard opent weer op stap 0;
  * de `required`-controle in `forms/service.py` overgeslagen → de tweede valt om.
"""
import re

import pytest

pytestmark = pytest.mark.ui_serverrendered


def _wizardformulier(client, admin_headers):
    """Twee secties: de eerste vrijblijvend, de tweede met een verplichte vraag."""
    payload = {
        "title": "Wizard met verplicht veld", "status": "open",
        "sections": [{"title": "Eerst", "position": 0},
                     {"title": "Daarna", "position": 1}],
        "fields": [
            {"field_type": "text", "label": "Vrijblijvend", "position": 0,
             "required": False, "section_index": 0},
            {"field_type": "text", "label": "Moet ingevuld", "position": 1,
             "required": True, "section_index": 1},
        ],
    }
    resp = client.post("/api/v1/forms", json=payload, headers=admin_headers)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _startstap(html: str) -> int:
    """De tweede parameter van formWizard(...) uit de gerenderde pagina."""
    treffer = re.search(r"formWizard\(.*?,\s*(\d+)\)", html)
    assert treffer, "de wizard wordt niet met een beginstap aangeroepen"
    return int(treffer.group(1))


def test_de_wizard_opent_op_de_stap_van_het_gemelde_veld(client, admin_headers,
                                                         db_session):
    form = _wizardformulier(client, admin_headers)
    verplicht = next(f for f in form["fields"] if f["required"])

    resp = client.post(f"/formulier/{form['share_token']}", data={
        "submitter_name": "Jan", "submitter_email": "jan@example.com",
        f"f{form['fields'][0]['id']}": "iets"})

    assert resp.status_code == 200, resp.text
    assert verplicht["label"] in resp.text, "de melding noemt het veld niet"
    assert _startstap(resp.text) == 1, (
        "de wizard opent op stap 0 — een melding over een vraag die je niet ziet")


def test_zonder_fout_begint_de_wizard_gewoon_vooraan(client, admin_headers):
    """De tegenhanger: bij het openen is stap 0 juist het goede antwoord."""
    form = _wizardformulier(client, admin_headers)

    resp = client.get(f"/formulier/{form['share_token']}")

    assert _startstap(resp.text) == 0


def test_rechtstreeks_verzenden_wordt_nog_steeds_geweigerd(client, admin_headers,
                                                           db_session):
    """De stapcontrole in de browser vervángt de server niet.

    Zonder deze test zou #724 ook "opgelost" zijn door alleen JavaScript toe te
    voegen — en dan komt een post die daar langs gaat gewoon binnen.
    """
    from app.domains.forms.models import FormSubmission

    form = _wizardformulier(client, admin_headers)

    resp = client.post(f"/formulier/{form['share_token']}", data={
        "submitter_name": "Jan", "submitter_email": "jan@example.com"})

    assert resp.status_code == 200, "de foutweg rendert de pagina opnieuw"
    assert "verplicht" in resp.text.lower()
    assert db_session.query(FormSubmission).filter(
        FormSubmission.form_id == form["id"]).count() == 0, (
        "de onvolledige inzending is toch bewaard")


def test_de_stappen_dragen_hun_verplichte_velden(client, admin_headers):
    """De wizard kan alleen per stap controleren als hij weet wat verplicht is.

    Het `required`-attribuut staat er bewust niet op (#688), dus die lijst moet uit
    de servercontext komen. Zonder haar is de controle in `next()` een lege huls.
    """
    form = _wizardformulier(client, admin_headers)
    verplicht = next(f for f in form["fields"] if f["required"])

    html = client.get(f"/formulier/{form['share_token']}").text

    stappen = re.search(r"formWizard\((\[.*?\]),\s*\d+\)", html)
    assert stappen, "de stappenlijst staat niet in de pagina"
    assert f'"req": [{verplicht["id"]}]' in stappen.group(1).replace("&#34;", '"') \
        or f'&#34;req&#34;: [{verplicht["id"]}]' in stappen.group(1), stappen.group(1)
