"""Tenant-instellingen-scherm (/admin/instellingen) — OPERATOR-only beheer
van de per-tenant config, incl. versleutelde secrets."""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.auth.models import User, UserRole
from app.kernel.tenancy import TENANT_VOORBEELD_ID
from app.kernel.tenant_config import TenantSetting, get_setting


def _login(client, db_session, *, operator: bool) -> str:
    if operator:
        user = (db_session.query(User)
                .filter(User.email == SEEDED_ADMIN_EMAIL).one())
        bestaat = (db_session.query(UserRole)
                   .filter_by(user_id=user.id, role_code="OPERATOR").first())
        if not bestaat:
            db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
            db_session.commit()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_scherm_is_operator_only(client, db_session):
    assert client.get("/admin/instellingen").status_code == 401
    # ADMIN zonder OPERATOR: 403 — eerst eventuele OPERATOR-rol weghalen
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    (db_session.query(UserRole)
     .filter_by(user_id=user.id, role_code="OPERATOR").delete())
    db_session.commit()
    _login(client, db_session, operator=False)
    assert client.get("/admin/instellingen").status_code == 403


def test_instellingen_opslaan_en_secret(client, db_session):
    csrf = _login(client, db_session, operator=True)
    resp = client.get(f"/admin/instellingen?tenant={TENANT_VOORBEELD_ID}")
    assert resp.status_code == 200 and "Tenant-instellingen" in resp.text

    resp = client.post(f"/admin/instellingen/{TENANT_VOORBEELD_ID}", data={
        "display_name": "Raak Testafdeling", "mail_mode": "log_only",
        "mollie_api_key": "test_sleutel123"},
        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "opgeslagen" in resp.text.lower()
    assert get_setting(db_session, "display_name",
                       tenant_id=TENANT_VOORBEELD_ID) == "Raak Testafdeling"
    rij = (db_session.query(TenantSetting)
           .filter_by(tenant_id=TENANT_VOORBEELD_ID, key="mollie_api_key").one())
    assert rij.value_encrypted and "test_sleutel123" not in (rij.value_encrypted or "")
    # de key wordt nooit teruggetoond
    assert "test_sleutel123" not in resp.text

    # leeg veld = sleutel wissen; secret leeg laten = ongewijzigd
    resp = client.post(f"/admin/instellingen/{TENANT_VOORBEELD_ID}", data={
        "display_name": ""}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert get_setting(db_session, "display_name",
                       tenant_id=TENANT_VOORBEELD_ID) is None
    assert get_setting(db_session, "mollie_api_key",
                       tenant_id=TENANT_VOORBEELD_ID) == "test_sleutel123"


def test_raakje_heeft_sprekknop(client):
    resp = client.get("/raakje")
    assert resp.status_code == 200
    if "niet beschikbaar" not in resp.text:
        assert "data-stt-target" in resp.text and "/static/stt.js" in resp.text
