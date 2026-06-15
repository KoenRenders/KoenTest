"""#151 — versie/commit zichtbaar via /api/health.

Invariant: de health-respons draagt altijd version + commit (fallback 'onbekend'),
zodat in elke deploy HTTP-verifieerbaar is welke release draait — zonder
servertoegang en zonder een crash als de build-info ontbreekt.
"""


def test_health_reports_version_and_commit(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # Velden aanwezig en nooit leeg (default 'onbekend' zonder build-info).
    assert body["version"]
    assert body["commit"]
