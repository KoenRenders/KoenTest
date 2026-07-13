"""React-exit 405-c1: publieke formulier-render (/formulier/{token}) —
alle veldtypes, validatie via de servicelaag, edit-flow."""
from app.domains.forms.models import Form, FormField, FormFieldOption, FormSubmission


def _form(db, **kwargs):
    defaults = dict(title="Testformulier", share_token="tok-render-1",
                    status="open", allow_edit=True)
    defaults.update(kwargs)
    f = Form(**defaults)
    db.add(f)
    db.flush()
    return f


def test_formulier_render_alle_types(client, db_session):
    f = _form(db_session)
    db_session.add(FormField(form_id=f.id, field_type="text", label="Naam ploeg",
                             required=True, position=0))
    veld_keuze = FormField(form_id=f.id, field_type="radio", label="Maat", position=1)
    db_session.add(veld_keuze)
    db_session.flush()
    db_session.add(FormFieldOption(field_id=veld_keuze.id, label="M", position=0))
    db_session.add(FormField(form_id=f.id, field_type="rating", label="Score", position=2))
    db_session.flush()

    page = client.get(f"/formulier/{f.share_token}")
    assert page.status_code == 200
    assert "Naam ploeg" in page.text and "Maat" in page.text and "Score" in page.text
    assert 'name="submitter_name"' in page.text  # contactblok (niet anoniem)


def test_formulier_submit_en_validatie(client, db_session):
    f = _form(db_session, share_token="tok-render-2")
    veld = FormField(form_id=f.id, field_type="text", label="Verplicht ding",
                     required=True, position=0)
    db_session.add(veld)
    db_session.flush()

    # Verplicht veld leeg → foutbanner, geen inzending.
    fout = client.post(f"/formulier/{f.share_token}",
                       data={"submitter_name": "Jo", "submitter_email": "jo@example.com"})
    assert fout.status_code == 200 and "verplicht" in fout.text
    assert db_session.query(FormSubmission).filter(FormSubmission.form_id == f.id).count() == 0

    ok = client.post(f"/formulier/{f.share_token}",
                     data={"submitter_name": "Jo", "submitter_email": "jo@example.com",
                           f"f{veld.id}": "Ingevuld!"})
    assert ok.status_code == 200 and "Bedankt" in ok.text
    sub = db_session.query(FormSubmission).filter(FormSubmission.form_id == f.id).one()
    assert sub.answers[0].value_text == "Ingevuld!"


def test_formulier_edit_flow(client, db_session):
    f = _form(db_session, share_token="tok-render-3")
    veld = FormField(form_id=f.id, field_type="text", label="Antwoord", position=0)
    db_session.add(veld)
    db_session.flush()
    client.post(f"/formulier/{f.share_token}",
                data={"submitter_name": "Mi", "submitter_email": "mi@example.com",
                      f"f{veld.id}": "Eerste versie"})
    sub = db_session.query(FormSubmission).filter(FormSubmission.form_id == f.id).one()
    assert sub.edit_token

    edit_page = client.get(f"/formulier/{f.share_token}/edit/{sub.edit_token}")
    assert edit_page.status_code == 200 and "Eerste versie" in edit_page.text

    resp = client.post(f"/formulier/{f.share_token}/edit/{sub.edit_token}",
                       data={"submitter_name": "Mi", "submitter_email": "mi@example.com",
                             f"f{veld.id}": "Tweede versie"})
    assert resp.status_code == 200 and "wijzigingen zijn opgeslagen" in resp.text.lower()
    db_session.expire_all()
    assert sub.answers[0].value_text == "Tweede versie"


def test_gesloten_formulier_geeft_403(client, db_session):
    f = _form(db_session, share_token="tok-render-4", status="closed")
    assert client.get(f"/formulier/{f.share_token}").status_code in (403, 404)
