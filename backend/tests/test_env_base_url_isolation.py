"""Regressie (#477): OMGEVINGEN MOGEN NOOIT MIXEN.

Een prod-URL die in de HDEV/UAT-database staat (seed/restore) mag nooit in een
absolute URL van een niet-prod-omgeving lekken — anders wijst de inloglink
(magic-link) of de Mollie-redirect op HDEV/UAT naar productie. `tenant_base_url`
is de enige bron van die origin; in niet-prod wint de env FRONTEND_URL altijd.
"""
import pytest

from app.config import settings
from app.kernel.tenant_config import set_setting, tenant_base_url

PROD_URL = "https://raakmillegem.be"


@pytest.mark.parametrize("env", ["hdev", "uat", "dev", "staging"])
def test_nonprod_never_uses_db_base_url(db_session, monkeypatch, env):
    """Met een prod-URL in de DB blijft een niet-prod-omgeving bij FRONTEND_URL."""
    monkeypatch.setattr(settings, "app_env", env)
    monkeypatch.setattr(settings, "frontend_url", "http://hdev.local:8081")
    set_setting(db_session, "base_url", PROD_URL)  # prod-URL sluipt in de DB
    db_session.flush()

    resultaat = tenant_base_url(db_session)
    assert resultaat == "http://hdev.local:8081"
    assert PROD_URL not in resultaat


def test_nonprod_magic_link_stays_on_hdev_origin(db_session, monkeypatch):
    """De concrete inloglink-opbouw (zoals in auth/router.py) blijft op HDEV."""
    monkeypatch.setattr(settings, "app_env", "hdev")
    monkeypatch.setattr(settings, "frontend_url", "http://128.0.0.1:8081")
    set_setting(db_session, "base_url", PROD_URL)
    db_session.flush()

    magic_link = f"{tenant_base_url(db_session)}/login/verify?token=abc"
    assert magic_link == "http://128.0.0.1:8081/login/verify?token=abc"
    assert "raakmillegem.be" not in magic_link


def test_prod_uses_db_base_url(db_session, monkeypatch):
    """In prod blijft de per-tenant DB-base_url leidend."""
    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "frontend_url", "http://fallback.invalid")
    set_setting(db_session, "base_url", PROD_URL)
    db_session.flush()

    assert tenant_base_url(db_session) == PROD_URL


def test_prod_falls_back_to_frontend_url_when_unset(db_session, monkeypatch):
    """Prod zonder DB-base_url valt terug op FRONTEND_URL (met rstrip)."""
    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "frontend_url", "https://raakmillegem.be/")
    # geen base_url-setting gezet
    assert tenant_base_url(db_session) == "https://raakmillegem.be"
