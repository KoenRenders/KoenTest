"""De interactieve API-docs en het OpenAPI-schema horen in prod-achtige
omgevingen verborgen te zijn (#269): geen datalek, maar wel een onnodige
API-kaart voor aanvallers."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import _docs_kwargs


def _client(app_env: str) -> TestClient:
    return TestClient(FastAPI(**_docs_kwargs(app_env)))


def test_docs_hidden_in_prod():
    c = _client("prod")
    assert c.get("/openapi.json").status_code == 404
    assert c.get("/docs").status_code == 404
    assert c.get("/redoc").status_code == 404


def test_docs_hidden_in_uat():
    assert _client("uat").get("/openapi.json").status_code == 404


def test_docs_visible_in_dev():
    assert _client("dev").get("/openapi.json").status_code == 200


def test_docs_visible_in_hdev():
    assert _client("hdev").get("/openapi.json").status_code == 200
