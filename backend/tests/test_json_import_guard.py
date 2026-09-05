"""#665 — een JSON-import mag geen antwoorden wissen.

`FormSubmissionAnswer.field_id` verwijst met `ondelete="CASCADE"` naar
`form_fields.id`, en `apply_definition` verwijdert elk veld dat niet meer in de
payload staat. Een JSON uit de AI-formaatgids bevat géén veld-id's, dus élk
bestaand veld geldt als "verdwenen" — en de CASCADE neemt alle antwoorden mee.
Er faalt niets, er verdwijnt alleen data.

De assert die telt is dus niet de statuscode maar het **aantal antwoorden erna**.
"""
import io
import json

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

_TELLER = 0


def _uniek(voorvoegsel: str) -> str:
    """Slug en share_token zijn uniek; elke test maakt haar eigen formulier."""
    global _TELLER
    _TELLER += 1
    return f"{voorvoegsel}-665-{_TELLER}"


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _formulier_met_inzending(db):
    """Een formulier met één veld en één ingevuld antwoord."""
    from app.domains.forms.models import (Form, FormField, FormSubmission,
                                          FormSubmissionAnswer)

    # share_token is NOT NULL en uniek: de app zet hem bij het aanmaken, dus een
    # fixture die het model rechtstreeks gebruikt moet dat zelf doen.
    form = Form(title="Bevraging", slug=_uniek("bevraging"), status="open",
                share_token=_uniek("tok"))
    db.add(form)
    db.flush()
    veld = FormField(form_id=form.id, label="Je naam", field_type="text", position=0)
    db.add(veld)
    db.flush()
    inzending = FormSubmission(form_id=form.id)
    db.add(inzending)
    db.flush()
    db.add(FormSubmissionAnswer(submission_id=inzending.id, field_id=veld.id,
                                value="Jef"))
    db.commit()
    return form, veld


def _antwoorden(db, form_id):
    from app.domains.forms.models import FormSubmission, FormSubmissionAnswer

    return (db.query(FormSubmissionAnswer)
            .join(FormSubmission,
                  FormSubmissionAnswer.submission_id == FormSubmission.id)
            .filter(FormSubmission.form_id == form_id)
            .count())


PAYLOAD = json.dumps({
    "title": "Vervangen",
    "fields": [{"label": "Iets anders", "field_type": "text", "position": 0}],
})


def test_import_op_een_formulier_met_inzendingen_wist_niets(client, db_session):
    """De invariant die vandaag stukgaat."""
    form, _veld = _formulier_met_inzending(db_session)
    csrf = _login(client)
    assert _antwoorden(db_session, form.id) == 1

    r = client.post(f"/admin/formulieren/{form.id}/json-import",
                    data={"payload": PAYLOAD}, headers={"X-CSRF-Token": csrf})

    assert r.status_code == 200
    db_session.expire_all()
    assert _antwoorden(db_session, form.id) == 1, (
        "de import heeft antwoorden verwijderd (#665)")
    assert "inzending" in r.text, "de weigering noemt de reden niet"


def test_de_weigering_noemt_het_aantal(client, db_session):
    form, _veld = _formulier_met_inzending(db_session)
    csrf = _login(client)
    r = client.post(f"/admin/formulieren/{form.id}/json-import",
                    data={"payload": PAYLOAD}, headers={"X-CSRF-Token": csrf})
    assert "1 inzending" in r.text


def test_zonder_inzendingen_werkt_de_import_gewoon(client, db_session):
    from app.domains.forms.models import Form, FormField

    form = Form(title="Leeg", slug=_uniek("leeg"), status="draft",
                share_token=_uniek("tok"))
    db_session.add(form)
    db_session.flush()
    db_session.add(FormField(form_id=form.id, label="Oud veld",
                             field_type="text", position=0))
    db_session.commit()
    csrf = _login(client)

    r = client.post(f"/admin/formulieren/{form.id}/json-import",
                    data={"payload": PAYLOAD}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    db_session.expire_all()
    db_session.refresh(form)
    assert form.title == "Vervangen"
    assert [f.label for f in form.fields] == ["Iets anders"]


def test_een_bestand_werkt_en_primeert_op_het_tekstvak(client, db_session):
    """Zoals een opgeladen affiche primeert op de poster-URL (#223)."""
    from app.domains.forms.models import Form

    form = Form(title="Leeg2", slug=_uniek("leeg2"), status="draft",
                share_token=_uniek("tok"))
    db_session.add(form)
    db_session.commit()
    csrf = _login(client)

    uit_bestand = json.dumps({"title": "Uit het bestand", "fields": []})
    r = client.post(f"/admin/formulieren/{form.id}/json-import",
                    data={"payload": json.dumps({"title": "Uit het tekstvak",
                                                 "fields": []})},
                    files={"file": ("def.json", io.BytesIO(uit_bestand.encode()),
                                    "application/json")},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    db_session.expire_all()
    db_session.refresh(form)
    assert form.title == "Uit het bestand"


def test_leeg_verzoek_geeft_een_nette_melding(client, db_session):
    from app.domains.forms.models import Form

    form = Form(title="Leeg3", slug=_uniek("leeg3"), status="draft",
                share_token=_uniek("tok"))
    db_session.add(form)
    db_session.commit()
    csrf = _login(client)

    r = client.post(f"/admin/formulieren/{form.id}/json-import",
                    data={"payload": "   "}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and "Plak een JSON-definitie" in r.text


def test_het_scherm_verbergt_de_import_bij_inzendingen(client, db_session):
    """Verbergen is geen guard, maar het hoort er wel bij: geen knop die de
    server toch weigert."""
    form, _veld = _formulier_met_inzending(db_session)
    _login(client)
    html = client.get(f"/admin/formulieren/{form.id}").text
    assert "Niet beschikbaar" in html
    assert 'name="payload"' not in html, "het invulvak staat er nog"
