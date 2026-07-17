"""Blok P (#398): berichten-capture → SubmissionCreated → behartigen-taak, en de
werkbank (sessie-auth, CSRF, sluiten-door-beslissing)."""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.forms.models import Form, FormSubmission
from app.domains.workflow.models import WorkflowTask
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _post_bericht(client, naam="Fee", email="fee@example.com", bericht="Meer wandelingen!"):
    return client.post("/berichten", data={"naam": naam, "email": email, "bericht": bericht})


def test_berichten_form_is_seeded(db_session):
    form = db_session.query(Form).filter(Form.slug == "berichten").one()
    assert form.status == "open" and form.send_confirmation is True
    assert form.fields[0].field_type == "textarea"


def test_bericht_creates_submission_and_task(client, db_session):
    resp = _post_bericht(client)
    # Na indienen: HX-Redirect terug naar de homepage met bedankt-flash (#451).
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == "/?bericht=verzonden"

    sub = db_session.query(FormSubmission).order_by(FormSubmission.id.desc()).first()
    assert sub.submitter_name == "Fee" and sub.answers[0].value_text == "Meer wandelingen!"

    task = db_session.query(WorkflowTask).order_by(WorkflowTask.id.desc()).first()
    assert task.kind == "bericht.behartigen" and task.status == "open"
    assert task.subject_id == sub.id and "Fee" in task.title


def test_bericht_requires_name_and_message(client, db_session):
    before = db_session.query(FormSubmission).count()
    resp = _post_bericht(client, naam="", bericht="")
    assert resp.status_code == 200 and "Vul je naam, een geldig e-mailadres en je bericht in" in resp.text
    # #501: ook een ontbrekend/ongeldig e-mailadres wordt geweigerd.
    resp2 = _post_bericht(client, naam="Jan", email="geen-apestaart", bericht="Hoi")
    assert resp2.status_code == 200 and "geldig e-mailadres" in resp2.text
    assert db_session.query(FormSubmission).count() == before


def test_werkbank_requires_session(client):
    assert client.get("/admin/werkbank").status_code == 401


def test_werkbank_lists_and_closes_task(client, db_session):
    _post_bericht(client, naam="Roos", bericht="Idee: zomerbar!")
    csrf = _login(client)

    page = client.get("/admin/werkbank")
    assert page.status_code == 200 and "Roos" in page.text and "Behartigen" in page.text

    task = db_session.query(WorkflowTask).order_by(WorkflowTask.id.desc()).first()
    detail = client.get(f"/admin/werkbank/taken/{task.id}")
    assert detail.status_code == 200 and "zomerbar" in detail.text

    done = client.post(f"/admin/werkbank/taken/{task.id}/afgehandeld",
                       data={"besluit": "Doorgegeven aan het bestuur"},
                       headers={"X-CSRF-Token": csrf})
    assert done.status_code == 200
    db_session.expire_all()
    assert task.status == "done" and task.done_by == SEEDED_ADMIN_EMAIL
    assert task.decision == "Doorgegeven aan het bestuur"


def test_afhandelen_without_csrf_fails(client, db_session):
    _post_bericht(client, naam="Saar", bericht="Test")
    _login(client)
    task = db_session.query(WorkflowTask).order_by(WorkflowTask.id.desc()).first()
    resp = client.post(f"/admin/werkbank/taken/{task.id}/afgehandeld", data={})
    assert resp.status_code == 403
    db_session.expire_all()
    assert task.status == "open"


def test_verify_otp_sets_session_cookie(client, db_session, monkeypatch):
    from app.domains.auth import router as auth_router
    monkeypatch.setattr(auth_router, "_generate_otp", lambda: "424242")
    client.post("/api/v1/auth/request-login", json={"email": SEEDED_ADMIN_EMAIL})
    resp = client.post("/api/v1/auth/verify-otp",
                       json={"email": SEEDED_ADMIN_EMAIL, "code": "424242"})
    assert resp.status_code == 200
    assert SESSION_COOKIE in resp.cookies
