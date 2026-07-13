"""Fase 1b (#399, §19.3): statische API-keys voor machine-consumenten."""
import pytest
from fastapi import HTTPException

from app.domains.auth.api import ApiKey, hash_api_key, require_api_key


class _FakeRequest:
    def __init__(self, key=None):
        self.headers = {"x-api-key": key} if key else {}


def test_admin_can_create_and_list_api_keys(client, admin_headers, db_session):
    resp = client.post("/api/v1/auth/api-keys", headers=admin_headers,
                       json={"name": "n8n-automations"})
    assert resp.status_code == 201
    body = resp.json()
    # De key zelf komt exact één keer terug; opgeslagen wordt enkel de hash.
    assert body["api_key"] and body["name"] == "n8n-automations"
    row = db_session.query(ApiKey).filter(ApiKey.name == "n8n-automations").one()
    assert row.key_hash == hash_api_key(body["api_key"])
    assert body["api_key"] not in (row.key_hash, row.name)

    listed = client.get("/api/v1/auth/api-keys", headers=admin_headers).json()
    assert any(k["name"] == "n8n-automations" for k in listed)
    assert all("api_key" not in k and "key_hash" not in k for k in listed)


def test_api_key_endpoints_require_admin(client):
    assert client.get("/api/v1/auth/api-keys").status_code == 401
    assert client.post("/api/v1/auth/api-keys", json={"name": "x"}).status_code == 401


def test_require_api_key_accepts_valid_and_rejects_invalid(client, admin_headers, db_session):
    key = client.post("/api/v1/auth/api-keys", headers=admin_headers,
                      json={"name": "consumer"}).json()["api_key"]

    entry = require_api_key(_FakeRequest(key), db_session)
    assert entry.name == "consumer" and entry.last_used_at is not None

    with pytest.raises(HTTPException) as exc:
        require_api_key(_FakeRequest("verkeerde-key"), db_session)
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException) as exc:
        require_api_key(_FakeRequest(None), db_session)
    assert exc.value.status_code == 401


def test_revoked_api_key_is_rejected(client, admin_headers, db_session):
    created = client.post("/api/v1/auth/api-keys", headers=admin_headers,
                          json={"name": "oud"}).json()
    assert client.delete(f"/api/v1/auth/api-keys/{created['id']}",
                         headers=admin_headers).status_code == 204
    db_session.expire_all()
    with pytest.raises(HTTPException) as exc:
        require_api_key(_FakeRequest(created["api_key"]), db_session)
    assert exc.value.status_code == 401
