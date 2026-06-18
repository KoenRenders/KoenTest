"""De dev-origin localhost:3000 hoort niet in de CORS-config van prod-achtige
omgevingen (#271): onnodig aanvalsoppervlak op de prod-API."""
from app.main import cors_origins


def test_localhost_excluded_in_prod():
    origins = cors_origins("prod", "https://raak.example")
    assert "http://localhost:3000" not in origins
    assert "https://raak.example" in origins


def test_localhost_excluded_in_uat():
    assert "http://localhost:3000" not in cors_origins("uat", "https://raak.example")


def test_localhost_included_in_dev():
    assert "http://localhost:3000" in cors_origins("dev", "https://raak.example")


def test_localhost_included_in_hdev():
    assert "http://localhost:3000" in cors_origins("hdev", "https://raak.example")
