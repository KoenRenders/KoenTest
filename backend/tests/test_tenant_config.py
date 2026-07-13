"""Fase 5b (#406): per-tenant config/secrets, demo-mail-modus (log_only),
per-tenant Mollie-key/base-URL en de OPERATOR-platformrol."""
from app.domains.auth.models import User, UserRole
from app.domains.auth.service import create_access_token
from app.domains.mail.models import EmailLog
from app.kernel.tenancy import TENANT_VOORBEELD_ID, current_tenant_id
from app.kernel.tenant_config import (
    TenantSetting,
    get_setting,
    set_setting,
    tenant_base_url,
    tenant_mail_mode,
    tenant_mollie_key,
)


def test_setting_plain_en_secret(db_session):
    set_setting(db_session, "display_name", "Testafdeling", tenant_id=99)
    set_setting(db_session, "mollie_api_key", "test_geheim123", secret=True, tenant_id=99)
    db_session.flush()

    assert get_setting(db_session, "display_name", tenant_id=99) == "Testafdeling"
    assert get_setting(db_session, "mollie_api_key", tenant_id=99) == "test_geheim123"

    # secret staat versleuteld op rust: nooit als klartekst in de rij
    rij = (db_session.query(TenantSetting)
           .filter_by(tenant_id=99, key="mollie_api_key").one())
    assert rij.value is None
    assert rij.value_encrypted and "test_geheim123" not in rij.value_encrypted

    # overschrijven en wissen
    set_setting(db_session, "display_name", None, tenant_id=99)
    db_session.flush()
    assert get_setting(db_session, "display_name", "fallback", tenant_id=99) == "fallback"


def test_env_defaults(db_session):
    from app.config import settings

    # zonder DB-waarde vallen de helpers terug op de .env-settings
    assert tenant_base_url(db_session, tenant_id=98) == settings.frontend_url.rstrip("/")
    assert tenant_mollie_key(db_session, tenant_id=98) == settings.mollie_api_key
    assert tenant_mail_mode(db_session, tenant_id=98) == "send"


def test_demo_tenant_seed(db_session):
    # migratie 087 seedt de voorbeeldafdeling: mails enkel loggen + noindex
    assert tenant_mail_mode(db_session, tenant_id=TENANT_VOORBEELD_ID) == "log_only"
    assert get_setting(db_session, "noindex", tenant_id=TENANT_VOORBEELD_ID) == "1"
    assert "renko.be/raakvoorbeeldafdeling" in tenant_base_url(
        db_session, tenant_id=TENANT_VOORBEELD_ID)


def test_demo_mails_worden_enkel_gelogd(db_session):
    from app.domains.mail.service import send_magic_link

    token = current_tenant_id.set(TENANT_VOORBEELD_ID)
    try:
        send_magic_link("demo@example.com", "https://renko.be/x")
    finally:
        current_tenant_id.reset(token)

    log = (db_session.query(EmailLog)
           .execution_options(include_all_tenants=True)
           .filter(EmailLog.recipient == "demo@example.com")
           .order_by(EmailLog.id.desc()).first())
    assert log is not None and log.status == "logged"
    assert log.tenant_id == TENANT_VOORBEELD_ID


def test_operator_passeert_elke_rolcheck(client, db_session):
    user = User(email="operator@example.com", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
    db_session.commit()

    token = create_access_token({"sub": "operator@example.com"})
    resp = client.get("/api/v1/admin/stats",
                      headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
