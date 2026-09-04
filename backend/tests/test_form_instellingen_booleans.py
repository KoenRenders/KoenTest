"""Instellingen van een formulier: geen boolean valt stil om (#629).

`requires_login` bestond op het model, in het schema en in de route — maar niet in het
formulier. `bool(Form(""))` is `False`, dus élke keer dat een beheerder "Instellingen
opslaan" klikte, ook voor een andere wijziging, viel die beveiligingsinstelling om
zonder melding. Dat is de vervelendste soort fout: je doet niets verkeerd.

De laatste test is de structurele bewaker: hij vergelijkt wat de route accepteert met
wat het formulier verstuurt, zodat een vergeten checkbox opvalt vóór ze data vernietigt.
"""
import inspect
import re
from pathlib import Path

import pytest

from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for, make_session_value)
from app.domains.forms.api import Form
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

TEMPLATE = (Path(__file__).resolve().parents[1] / "app" / "domains" / "forms"
            / "templates" / "_fb_builder.html")
BOOLEANS = ("send_confirmation", "allow_edit", "is_anonymous", "requires_login")


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _formulier(db, **kw):
    form = Form(title="Instellingen", share_token=f"tok-{kw.get('n', 1)}", status="draft", **{
        k: v for k, v in kw.items() if k != "n"})
    db.add(form)
    db.commit()
    return form


def test_requires_login_blijft_staan_na_opslaan(client, db_session):
    """De regressie zelf: bewaren met de checkbox aangevinkt mag hem niet uitzetten."""
    form = _formulier(db_session, requires_login=True, n=1)
    hdr = _login(client)

    resp = client.post(f"/admin/formulieren/{form.id}/instellingen", headers=hdr, data={
        "title": "Instellingen", "status": "draft", "requires_login": "1"})
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    assert db_session.get(Form, form.id).requires_login is True


def test_de_checkbox_staat_in_het_formulier_met_de_juiste_stand(client, db_session):
    """Zonder checkbox stuurt het formulier het veld nooit mee, en dan is elke
    opslag een stille uitschakeling."""
    form = _formulier(db_session, requires_login=True, n=2)
    _login(client)

    html = client.get(f"/admin/formulieren/{form.id}").text
    assert 'name="requires_login"' in html
    checkbox = [r for r in html.splitlines() if 'name="requires_login"' in r][0]
    assert "checked" in checkbox, "de stand van de databank hoort weerspiegeld te worden"


@pytest.mark.parametrize("veld", BOOLEANS)
def test_elke_boolean_is_uit_te_zetten_en_aan_te_zetten(client, db_session, veld):
    form = _formulier(db_session, n=f"aan-{veld}", **{veld: False})
    hdr = _login(client)
    basis = {"title": "Instellingen", "status": "draft"}

    client.post(f"/admin/formulieren/{form.id}/instellingen", headers=hdr,
                data={**basis, veld: "1"})
    db_session.expire_all()
    assert getattr(db_session.get(Form, form.id), veld) is True

    client.post(f"/admin/formulieren/{form.id}/instellingen", headers=hdr, data=basis)
    db_session.expire_all()
    assert getattr(db_session.get(Form, form.id), veld) is False


def test_elke_boolean_die_de_route_wegschrijft_heeft_een_invoerveld():
    """De structurele bewaker (#629).

    Ik heb bewust NIET de voorgestelde verborgen input vóór elke checkbox gebruikt: een
    hidden veld met een lege waarde levert `bool("")` → `False`, dus het lost precies
    niets op bij een vergeten checkbox. Wat wél werkt is deze vergelijking — wat de
    route accepteert tegenover wat het formulier verstuurt.
    """
    from app.domains.forms.admin_ui import instellingen_opslaan

    accepteert = set(inspect.signature(instellingen_opslaan).parameters)
    booleans = {v for v in BOOLEANS if v in accepteert}
    assert booleans == set(BOOLEANS), f"route accepteert niet alle booleans: {booleans}"

    template = TEMPLATE.read_text()
    velden = set(re.findall(r'name="([a-z_]+)" value="1"', template))
    ontbreekt = sorted(booleans - velden)
    assert not ontbreekt, (
        "de route schrijft deze booleans weg maar het formulier stuurt ze niet mee — "
        f"elke opslag zet ze stil op False: {ontbreekt}"
    )
