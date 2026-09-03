"""Tenantbeheer (/admin/tenants) — OPERATOR-only, één scherm voor één object (#581).

Vroeger stonden de tenant-lijst en de tenant-settings op twee schermen, met een
"Afdeling"-dropdown als tweede manier om een tenant te kiezen. Deze tests leggen
vast wat daarbij niet mag sneuvelen: de OPERATOR-poort, dat settings echt
persisteren (inclusief het versleutelde secret dat nooit teruggetoond wordt), en
dat de oude URL blijft werken.
"""
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


def _zonder_operator(db_session):
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    (db_session.query(UserRole)
     .filter_by(user_id=user.id, role_code="OPERATOR").delete())
    db_session.commit()


def test_lijst_en_editor_zijn_operator_only(client, db_session):
    """Beide schermen zitten achter dezelfde poort — de editor is niet de zwakke plek."""
    assert client.get("/admin/tenants").status_code == 401
    assert client.get(f"/admin/tenants/{TENANT_VOORBEELD_ID}").status_code == 401

    _zonder_operator(db_session)
    _login(client, db_session, operator=False)
    assert client.get("/admin/tenants").status_code == 403
    assert client.get(f"/admin/tenants/{TENANT_VOORBEELD_ID}").status_code == 403


def test_opslaan_via_de_editor_is_ook_operator_only(client, db_session):
    """Een ADMIN zonder OPERATOR mag settings niet wijzigen — ook niet met een geldig CSRF-token."""
    _zonder_operator(db_session)
    csrf = _login(client, db_session, operator=False)
    resp = client.post(f"/admin/tenants/{TENANT_VOORBEELD_ID}",
                       data={"display_name": "Gekaapt"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 403
    assert get_setting(db_session, "display_name",
                       tenant_id=TENANT_VOORBEELD_ID) != "Gekaapt"


def test_oude_instellingen_url_leidt_door(client, db_session):
    """De aparte Instellingen-pagina is opgegaan in /admin/tenants; bladwijzers blijven werken."""
    _login(client, db_session, operator=True)
    resp = client.get("/admin/instellingen", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/admin/tenants"


def test_lijst_toont_units_en_linkt_naar_de_editor(client, db_session):
    _login(client, db_session, operator=True)
    resp = client.get("/admin/tenants")
    assert resp.status_code == 200
    assert f'href="/admin/tenants/{TENANT_VOORBEELD_ID}"' in resp.text
    # Geen tweede tenant-kiezer meer: de dropdown "Afdeling" is verdwenen.
    assert 'name="tenant"' not in resp.text


def test_zoeken_filtert_de_lijst(client, db_session):
    _login(client, db_session, operator=True)
    alles = client.get("/admin/tenants").text
    assert f'href="/admin/tenants/{TENANT_VOORBEELD_ID}"' in alles
    geen = client.get("/admin/tenants?q=bestaatnietxyz").text
    assert f'href="/admin/tenants/{TENANT_VOORBEELD_ID}"' not in geen


def test_settings_persisteren_en_secret_blijft_geheim(client, db_session):
    csrf = _login(client, db_session, operator=True)
    resp = client.get(f"/admin/tenants/{TENANT_VOORBEELD_ID}")
    assert resp.status_code == 200 and "Instellingen van deze afdeling" in resp.text

    resp = client.post(f"/admin/tenants/{TENANT_VOORBEELD_ID}", data={
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
    resp = client.post(f"/admin/tenants/{TENANT_VOORBEELD_ID}", data={
        "display_name": ""}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert get_setting(db_session, "display_name",
                       tenant_id=TENANT_VOORBEELD_ID) is None
    assert get_setting(db_session, "mollie_api_key",
                       tenant_id=TENANT_VOORBEELD_ID) == "test_sleutel123"


def test_onbekende_tenant_geeft_404(client, db_session):
    _login(client, db_session, operator=True)
    assert client.get("/admin/tenants/999999").status_code == 404


def test_raakje_heeft_sprekknop(client):
    resp = client.get("/raakje")
    assert resp.status_code == 200
    if "niet beschikbaar" not in resp.text:
        assert "data-stt-target" in resp.text and "/static/stt.js" in resp.text
