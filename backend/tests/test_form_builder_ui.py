"""React-exit 405-c2: server-side form-builder (optie a) — secties/velden/opties
met op-aflopen en branching, JSON-import, inzendingen-tab, afdruk."""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.forms.models import Form, FormField, FormSection


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_builder_requires_session(client):
    assert client.get("/admin/formulieren").status_code == 401


def test_formulier_aanmaken_en_bouwen(client, db_session):
    csrf = _login(client)
    resp = client.post("/admin/formulieren", data={"title": "Kamp 2032"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "Kamp 2032" in resp.text
    form = db_session.query(Form).filter(Form.title == "Kamp 2032").one()

    # sectie + veld + optie
    client.post(f"/admin/formulieren/{form.id}/secties", data={"title": "Deel A"},
                headers={"X-CSRF-Token": csrf})
    db_session.expire_all()
    sectie = form.sections[0]
    client.post(f"/admin/formulieren/{form.id}/velden",
                data={"label": "Maat T-shirt", "field_type": "radio",
                      "section_id": str(sectie.id)},
                headers={"X-CSRF-Token": csrf})
    db_session.expire_all()
    veld = form.fields[0]
    optie_resp = client.post(f"/admin/formulieren/{form.id}/velden/{veld.id}/opties",
                             data={"label": "M"}, headers={"X-CSRF-Token": csrf})
    assert optie_resp.status_code == 200 and "Maat T-shirt" in optie_resp.text
    db_session.expire_all()
    assert veld.options[0].label == "M"

    # #524 (§10): de sectie rendert als een gekleurde header-balk met "Sectie X van N".
    assert "Sectie 1 van 1" in optie_resp.text
    assert "bg-blue-700" in optie_resp.text


def test_velden_verplaatsen(client, db_session):
    csrf = _login(client)
    form = Form(title="Volgorde", share_token="tok-builder-1", status="draft")
    db_session.add(form)
    db_session.flush()
    a = FormField(form_id=form.id, field_type="text", label="A", position=0)
    b = FormField(form_id=form.id, field_type="text", label="B", position=1)
    db_session.add_all([a, b])
    db_session.flush()

    resp = client.post(f"/admin/formulieren/{form.id}/velden/{b.id}/verplaats",
                       data={"richting": "op"}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    db_session.expire_all()
    assert (b.position, a.position) == (0, 1)


def test_branching_validatie(client, db_session):
    csrf = _login(client)
    form = Form(title="Branch", share_token="tok-builder-2", status="draft")
    db_session.add(form)
    db_session.flush()
    s1 = FormSection(form_id=form.id, title="Een", position=0)
    s2 = FormSection(form_id=form.id, title="Twee", position=1)
    db_session.add_all([s1, s2])
    db_session.flush()
    veld = FormField(form_id=form.id, field_type="radio", label="Keuze",
                     section_id=s2.id, position=0)
    db_session.add(veld)
    db_session.flush()
    client.post(f"/admin/formulieren/{form.id}/velden/{veld.id}/opties",
                data={"label": "Ja"}, headers={"X-CSRF-Token": csrf})
    db_session.expire_all()
    optie = veld.options[0]

    # Terug-sprong (naar sectie 1 vanaf sectie 2) → 422.
    fout = client.post(f"/admin/formulieren/{form.id}/opties/{optie.id}",
                       data={"label": "Ja", "skip_to_section_id": str(s1.id)},
                       headers={"X-CSRF-Token": csrf})
    assert fout.status_code == 422


def test_json_import_vluchtluik(client, db_session):
    csrf = _login(client)
    form = Form(title="Import", share_token="tok-builder-3", status="draft")
    db_session.add(form)
    db_session.flush()
    payload = '''{"title": "Geimporteerd", "status": "draft",
        "fields": [{"field_type": "text", "label": "Vraag 1", "required": true, "options": []}]}'''
    resp = client.post(f"/admin/formulieren/{form.id}/json-import",
                       data={"payload": payload}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "Vraag 1" in resp.text
    db_session.expire_all()
    assert form.title == "Geimporteerd" and form.fields[0].label == "Vraag 1"

    kapot = client.post(f"/admin/formulieren/{form.id}/json-import",
                        data={"payload": "{geen json"}, headers={"X-CSRF-Token": csrf})
    assert kapot.status_code == 200 and "Ongeldige JSON" in kapot.text


def test_inzendingen_en_afdruk(client, db_session):
    csrf = _login(client)
    form = Form(title="Met inzending", share_token="tok-builder-4", status="open")
    db_session.add(form)
    db_session.flush()
    veld = FormField(form_id=form.id, field_type="text", label="Iets", position=0)
    db_session.add(veld)
    db_session.flush()
    client.post(f"/formulier/{form.share_token}",
                data={"submitter_name": "Ines", "submitter_email": "ines@example.com",
                      f"f{veld.id}": "Antwoordtekst"})

    tab = client.get(f"/admin/formulieren/{form.id}/inzendingen")
    assert tab.status_code == 200 and "Ines" in tab.text and "Antwoordtekst" in tab.text

    afdruk = client.get(f"/admin/formulieren/{form.id}/afdruk")
    assert afdruk.status_code == 200 and "Iets" in afdruk.text and "print" in afdruk.text
