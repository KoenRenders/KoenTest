"""Fase 4c-3 (#404): analyse-dashboard met server-gerenderde SVG."""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, make_session_value


def test_analyse_requires_session(client):
    assert client.get("/admin/analyse").status_code == 401


def test_analyse_renders_svg_and_totals(client, db_session):
    from app.domains.analytics.api import log_business_event
    log_business_event(db_session, "inschrijving_voltooid", payload={"paid": False})
    db_session.flush()

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    page = client.get("/admin/analyse")
    assert page.status_code == 200
    assert "<svg" in page.text and "inschrijving_voltooid" in page.text
    assert "Omzet" in page.text
