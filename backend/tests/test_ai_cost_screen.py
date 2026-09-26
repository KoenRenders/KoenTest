"""The AI cost screen (#978): reachable from /admin/info, scoped, no payload.

Broken to see it red (measured): the link removed from `admin_info.html` →
the first test fails; `tenant_id=tenant` in `list_calls` replaced by another
department → the scope test fails; `payload` added to `CallRow` and rendered
→ the payload test fails.
"""
import pytest
from sqlalchemy import text as sql_text

from app.database import SessionLocal
from app.domains.chatbot.api import sink_for
from app.kernel.tenancy import DEFAULT_TENANT_ID
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def leeg_logboek():
    def wis():
        eigen = SessionLocal()
        try:
            eigen.execute(sql_text("DELETE FROM ai.ai_call_log"))
            eigen.commit()
        finally:
            eigen.close()

    wis()
    yield
    wis()


def _login(client):
    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _oproep(tenant_id, **extra):
    velden = dict(surface="admin", capability="reporting", model="mistral-medium",
                  payload="GEHEIME-PAYLOAD-978", provider="mistral",
                  endpoint="chat.completions", duration_ms=1234,
                  usage={"prompt": 100, "completion": 20}, tenant_id=tenant_id)
    velden.update(extra)
    sink_for("bestuur@example.org")(**velden)


def test_system_info_links_to_the_cost_screen(client):
    _login(client)
    resp = client.get("/admin/info")
    assert resp.status_code == 200
    assert 'href="/admin/info/ai-kosten"' in resp.text


def test_the_screen_shows_totals_and_calls_with_who_asked(client, leeg_logboek):
    _oproep(DEFAULT_TENANT_ID)
    _oproep(DEFAULT_TENANT_ID, provider="bfl", capability="image", model="flux-2-pro",
            cost_credits=4.5, cost_amount=0.045, cost_currency="USD", usage=None)
    _login(client)
    resp = client.get("/admin/info/ai-kosten")

    assert resp.status_code == 200
    html = resp.text
    assert "Totaal in" in html
    assert "0,0450 USD" in html and "4,50" in html
    assert "Rapporten" in html and "1,2 s" in html
    assert "bestuur@example.org" in html, "Koen: the list shows who asked"


def test_the_payload_never_reaches_the_screen(client, leeg_logboek):
    _oproep(DEFAULT_TENANT_ID)
    _login(client)
    for pad in ("/admin/info/ai-kosten", "/admin/info/ai-kosten?page=1"):
        resp = client.get(pad, headers={"HX-Request": "true"} if "page" in pad else {})
        assert resp.status_code == 200
        assert "mistral-medium" in resp.text, "the row itself is on the screen"
        assert "GEHEIME-PAYLOAD-978" not in resp.text


def test_another_department_is_not_on_the_screen(client, leeg_logboek):
    _oproep(DEFAULT_TENANT_ID, model="hier-model")
    _oproep(DEFAULT_TENANT_ID + 40, model="elders-model")
    _login(client)
    html = client.get("/admin/info/ai-kosten").text
    assert "hier-model" in html
    assert "elders-model" not in html


def test_the_screen_needs_an_admin(client):
    assert client.get("/admin/info/ai-kosten").status_code == 401
