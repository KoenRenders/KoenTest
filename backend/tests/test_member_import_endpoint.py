"""Tests voor de admin-upload-endpoints van het ledenrapport (#170).

De parsing zelf wordt voor de happy-path gemonkeypatcht (geen .xls nodig); de
foutpaden (ongeldig bestand, .xlsx) gebruiken de echte parser. De upsert-logica
is uitvoerig getest in test_member_import_upsert.py.
"""
import pytest

from app.models.member import Member
import app.routers.member_import as mi
from tests.conftest import seed_postal_code

PREVIEW = "/api/v1/admin/member-import/preview"
COMMIT = "/api/v1/admin/member-import/commit"


@pytest.fixture(autouse=True)
def _clear_pending():
    mi._PENDING.clear()
    yield
    mi._PENDING.clear()


def _row(lidnr, voornaam, naam, relatie="HOOFDLID", email=None):
    return {
        "lidnr": lidnr, "voornaam": voornaam, "naam": naam,
        "straat": "milostraat", "huisnummer": "40", "busnummer": "",
        "postcode": "2400", "gemeente": "Mol",
        "email": email, "telefoon": None, "gsm": None,
        "geboortedatum": None, "geslacht": None,
        "bestuurslid": None, "_relatie": relatie,
    }


def _fake_parse(families):
    def _inner(content, *, load_all):
        return families, {}, [], []
    return _inner


def _upload(client, headers, *, name="ledenrapport.xls", content=b"binary"):
    return client.post(
        PREVIEW,
        files={"file": (name, content, "application/vnd.ms-excel")},
        headers=headers,
    )


def test_preview_requires_admin(client):
    r = _upload(client, {})
    assert r.status_code in (401, 403)


def test_commit_requires_admin(client):
    r = client.post(COMMIT, json={"token": "x"})
    assert r.status_code in (401, 403)


def test_preview_then_commit_applies(client, db_session, admin_headers, monkeypatch):
    seed_postal_code(db_session)
    families = [[_row("100", "Jan", "Janssens", email="jan@example.com")]]
    monkeypatch.setattr(mi, "parse_families", _fake_parse(families))

    r = _upload(client, admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["report"]["new_families"] == 1
    assert body["selected_families"] == 1
    token = body["token"]
    # Dry-run: nog niets weggeschreven.
    assert db_session.query(Member).count() == 0

    r2 = client.post(COMMIT, json={"token": token}, headers=admin_headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["report"]["new_families"] == 1
    assert db_session.query(Member).count() == 1


def test_commit_unknown_token_404(client, admin_headers):
    r = client.post(COMMIT, json={"token": "bestaat-niet"}, headers=admin_headers)
    assert r.status_code == 404


def test_commit_expired_token_410(client, db_session, admin_headers, monkeypatch):
    families = [[_row("100", "Jan", "Janssens")]]
    monkeypatch.setattr(mi, "parse_families", _fake_parse(families))
    seed_postal_code(db_session)

    token = _upload(client, admin_headers).json()["token"]
    # Forceer verloop: zet de aanmaaktijd ver in het verleden.
    mi._PENDING[token]["created_at"] -= mi._TTL_SECONDS + 1

    r = client.post(COMMIT, json={"token": token}, headers=admin_headers)
    assert r.status_code == 410


def test_token_single_use(client, db_session, admin_headers, monkeypatch):
    families = [[_row("100", "Jan", "Janssens")]]
    monkeypatch.setattr(mi, "parse_families", _fake_parse(families))
    seed_postal_code(db_session)

    token = _upload(client, admin_headers).json()["token"]
    assert client.post(COMMIT, json={"token": token}, headers=admin_headers).status_code == 200
    # Tweede keer: token is verbruikt.
    assert client.post(COMMIT, json={"token": token}, headers=admin_headers).status_code == 404


def test_preview_invalid_file_400(client, admin_headers):
    r = _upload(client, admin_headers, content=b"dit is geen excel")
    assert r.status_code == 400


def test_preview_xlsx_rejected(client, admin_headers):
    r = _upload(client, admin_headers, name="ledenrapport.xlsx")
    assert r.status_code == 400


def test_preview_empty_file_400(client, admin_headers):
    r = _upload(client, admin_headers, content=b"")
    assert r.status_code == 400
