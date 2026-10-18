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
from tests.conftest import SEEDED_ADMIN_EMAIL, sent_to_sign_in

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
    velden = dict(
        surface="admin",
        capability="reporting",
        model="mistral-medium",
        payload="GEHEIME-PAYLOAD-978",
        provider="mistral",
        endpoint="chat.completions",
        duration_ms=1234,
        usage={"prompt": 100, "completion": 20},
        tenant_id=tenant_id,
    )
    velden.update(extra)
    sink_for("bestuur@example.org")(**velden)


def test_system_info_links_to_the_cost_screen(client):
    _login(client)
    resp = client.get("/admin/info")
    assert resp.status_code == 200
    assert 'href="/admin/info/ai-kosten"' in resp.text


def test_the_screen_shows_totals_and_calls_with_who_asked(client, leeg_logboek):
    _oproep(DEFAULT_TENANT_ID)
    _oproep(
        DEFAULT_TENANT_ID,
        provider="bfl",
        capability="image",
        model="flux-2-pro",
        cost_credits=4.5,
        cost_amount=0.045,
        cost_currency="USD",
        usage=None,
    )
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
    assert sent_to_sign_in(client, "/admin/info/ai-kosten")


def test_the_calls_stand_on_the_kits_table(client, leeg_logboek):
    """#1925 (Koen, 16 October 2026, "a"): eight values in the kit's seven places —
    the model and its provider in ONE optional column (priority 1, a wide screen),
    the duration in the other (priority 2)."""
    import re

    _oproep(DEFAULT_TENANT_ID)
    _login(client)
    html = client.get("/admin/info/ai-kosten").text
    assert "data-table" in html, "the kit's table"
    model = re.search(r'<th[^>]*data-p="1"[^>]*>\s*Model', html)
    duur = re.search(r'<th[^>]*data-p="2"[^>]*>\s*Duur', html)
    assert model and duur, "Model is priority 1 and Duur priority 2"
    assert "mistral-medium · Mistral" in html, "the model with its provider, one cell"
    calls = html.split('id="ai-oproepen"', 1)[1]
    assert ">Provider<" not in calls, "no column of its own for the provider in the list"


def test_the_toolbar_filters_the_calls_by_component_and_provider(client, leeg_logboek):
    """#2109: Onderdeel and Provider narrow the list — and only the list: the totals
    above it are the month's. Broken to see it red: `capability=` dropped from the
    `list_calls` call → the first assertion fails."""
    _oproep(DEFAULT_TENANT_ID, model="rapport-model")
    _oproep(DEFAULT_TENANT_ID, provider="bfl", capability="image", model="beeld-model")
    _login(client)
    fragment = {"HX-Request": "true"}
    both = client.get("/admin/info/ai-kosten/lijst", headers=fragment).text
    assert "rapport-model" in both and "beeld-model" in both
    by_component = client.get("/admin/info/ai-kosten/lijst?capability=image", headers=fragment).text
    assert "beeld-model" in by_component and "rapport-model" not in by_component
    by_provider = client.get("/admin/info/ai-kosten/lijst?provider=mistral", headers=fragment).text
    assert "rapport-model" in by_provider and "beeld-model" not in by_provider
    nothing = client.get("/admin/info/ai-kosten/lijst?provider=mistral&capability=image").text
    assert "Geen AI-oproepen voor deze filter" in nothing
    page = client.get("/admin/info/ai-kosten?capability=image").text
    assert "rapport-model" not in page and "Totaal in" in page
    assert 'name="q"' not in page, "AI-kosten has no search (§5.1)"
    assert "Beeld" in page and "ai-capability" in page and "ai-provider" in page


def test_the_month_arrows_and_the_date_sort_move_the_list(client, leeg_logboek):
    """#2109: ‹ › change the month of the totals AND of the calls; the date column
    sorts newest or oldest first and keeps the month."""
    _oproep(DEFAULT_TENANT_ID, model="eerste-model")
    _oproep(DEFAULT_TENANT_ID, model="tweede-model")
    eigen = SessionLocal()
    try:
        eigen.execute(
            sql_text(
                "UPDATE ai.ai_call_log SET created_at = '2026-03-10 12:00+00' "
                "WHERE model = 'eerste-model'"
            )
        )
        eigen.execute(
            sql_text(
                "UPDATE ai.ai_call_log SET created_at = '2026-03-20 12:00+00' "
                "WHERE model = 'tweede-model'"
            )
        )
        eigen.commit()
    finally:
        eigen.close()
    _login(client)
    maart = client.get("/admin/info/ai-kosten?maand=2026-03").text
    assert "eerste-model" in maart and "tweede-model" in maart
    assert "maand=2026-02" in maart and "maand=2026-04" in maart, "the ‹ › links"
    assert "eerste-model" not in client.get("/admin/info/ai-kosten?maand=2026-04").text
    newest = client.get("/admin/info/ai-kosten/lijst?maand=2026-03").text
    assert newest.index("tweede-model") < newest.index("eerste-model")
    oldest = client.get("/admin/info/ai-kosten/lijst?maand=2026-03&sort=datum").text
    assert oldest.index("eerste-model") < oldest.index("tweede-model")
    assert 'aria-sort="ascending"' in oldest
