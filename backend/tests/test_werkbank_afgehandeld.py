"""#674 — afgehandelde taken zijn terug te vinden, met hun besluit.

`WorkflowTask` bewaart `decision`, `done_by`, `done_at` en `status`, en
`complete_task` schrijft ze netjes weg — de docstring zegt zelfs "een afwijzing is
ook een beslissing: het besluit blijft bewaard". Maar `open_tasks` filtert hard op
`status == "open"`, dus zodra je Afgehandeld klikte verdween de taak inclusief het
antwoord dat je net intypte, en er was geen enkel scherm waar je hem terugvond.

Twee dingen die hier stil kapot kunnen gaan, en die deze tests vastzetten:

1. **`open_tasks` blijft exact wat ze was.** Ze voedt ook de idempotentie van de
   weesjob (die vergelijkt titels van OPEN taken om geen tweede aan te maken) en de
   navigatieteller. Verruimd naar alle statussen zou de weesjob geen taken meer
   aanmaken en zou de teller niet meer kloppen.
2. **De rolfilter geldt óók op afgehandelde taken**, anders lekt een FINANCE-taak
   naar een gewone admin zodra ze gesloten is.
"""
import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, csrf_token_for,
                                  make_session_value)
from app.domains.workflow import api
from app.domains.workflow.models import WorkflowTask
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _taak(db, *, titel="Bericht behartigen", rol="ADMIN", status="open"):
    taak = WorkflowTask(kind="bericht.behartigen", title=titel, status=status,
                        subject_type="form_submission", subject_id=1,
                        required_role=rol)
    db.add(taak)
    db.commit()
    return taak


def test_een_afgehandelde_taak_is_terug_te_vinden(client, db_session):
    taak = _taak(db_session, titel="Vraag over de barbecue")
    api.close_task(db_session, taak.id, done_by="koen@example.com",
                   decision="Telefonisch beantwoord, komt met twee personen")
    db_session.commit()
    _login(client)

    html = client.get("/admin/werkbank/lijst?status=done").text
    assert "Vraag over de barbecue" in html
    assert "Telefonisch beantwoord" in html, "het besluit staat er niet bij"
    assert "koen@example.com" in html, "wie het afhandelde staat er niet bij"


def test_de_open_lijst_blijft_de_open_lijst(client, db_session):
    open_taak = _taak(db_session, titel="Nog te doen")
    klaar = _taak(db_session, titel="Al gedaan")
    api.close_task(db_session, klaar.id, done_by="koen@example.com", decision="ok")
    db_session.commit()
    _login(client)

    html = client.get("/admin/werkbank/lijst").text
    assert "Nog te doen" in html and "Al gedaan" not in html


def test_alle_toont_beide(client, db_session):
    open_taak = _taak(db_session, titel="Nog te doen")
    klaar = _taak(db_session, titel="Al gedaan")
    api.close_task(db_session, klaar.id, done_by="koen@example.com", decision="ok")
    db_session.commit()
    _login(client)

    html = client.get("/admin/werkbank/lijst?status=all").text
    assert "Nog te doen" in html and "Al gedaan" in html


def test_open_tasks_blijft_onveranderd(db_session):
    """De regressie die de weesjob en de navigatieteller stil zou breken."""
    open_taak = _taak(db_session, titel="Nog te doen")
    klaar = _taak(db_session, titel="Al gedaan")
    api.close_task(db_session, klaar.id, done_by="koen@example.com", decision="ok")
    db_session.commit()

    titels = [t.title for t in api.open_tasks(db_session, ["ADMIN"])]
    assert "Nog te doen" in titels
    assert "Al gedaan" not in titels, (
        "open_tasks geeft nu ook afgehandelde taken terug — de weesjob maakt dan "
        "geen taken meer aan en de teller klopt niet")
    assert api.open_count(db_session, ["ADMIN"]) == len(titels)


def test_de_rolfilter_geldt_ook_op_afgehandelde_taken(db_session):
    """Anders lekt een FINANCE-taak naar een gewone admin zodra ze gesloten is."""
    geld = _taak(db_session, titel="Terugbetaling bevestigen", rol="FINANCE")
    api.close_task(db_session, geld.id, done_by="fin@example.com", decision="betaald")
    db_session.commit()

    voor_admin = [t.title for t in api.tasks(db_session, ["ADMIN"], status="done")]
    assert "Terugbetaling bevestigen" not in voor_admin

    voor_finance = [t.title for t in api.tasks(db_session, ["FINANCE"], status="done")]
    assert "Terugbetaling bevestigen" in voor_finance


def test_een_afgehandelde_taak_toont_geen_afhandelvorm(client, db_session):
    taak = _taak(db_session, titel="Al gedaan")
    api.close_task(db_session, taak.id, done_by="koen@example.com", decision="ok")
    db_session.commit()
    _login(client)

    html = client.get(f"/admin/werkbank/taken/{taak.id}").text
    assert "Besluit" in html and "ok" in html
    assert f"/admin/werkbank/taken/{taak.id}/afgehandeld" not in html, (
        "een afgehandelde taak biedt nog een afhandelknop aan")


def test_een_onbekende_status_valt_terug_op_open(client, db_session):
    _taak(db_session, titel="Nog te doen")
    klaar = _taak(db_session, titel="Al gedaan")
    api.close_task(db_session, klaar.id, done_by="k@example.com", decision="ok")
    db_session.commit()
    _login(client)

    html = client.get("/admin/werkbank/lijst?status=onzin").text
    assert "Nog te doen" in html and "Al gedaan" not in html
