"""The two steps of the member report's upload (#170): a preview that writes
nothing and hands out a token, and a commit that takes the token once.

Asked at the facade the import screen calls (`mdm.api.import_preview`,
`import_commit`); the JSON routes that passed the same calls on had no caller
and are gone (CR-13 phase 4b, #1251). The parsing itself is replaced for the
happy path (no .xls needed); the failure paths (an invalid file, .xlsx) use the
real parser. The upsert is tested in test_member_import_upsert.py.
"""

import asyncio
import io

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

import app.domains.mdm.import_router as mi
from app.domains.mdm.api import Member, import_commit, import_preview
from tests.conftest import seed_postal_code, seeded_admin


@pytest.fixture(autouse=True)
def _clear_pending():
    mi._PENDING.clear()
    yield
    mi._PENDING.clear()


def _row(lidnr, voornaam, naam, relatie="HOOFDLID", email=None):
    return {
        "lidnr": lidnr,
        "voornaam": voornaam,
        "naam": naam,
        "straat": "milostraat",
        "huisnummer": "40",
        "busnummer": "",
        "postcode": "2400",
        "gemeente": "Mol",
        "email": email,
        "telefoon": None,
        "gsm": None,
        "geboortedatum": None,
        "geslacht": None,
        "bestuurslid": None,
        "_relatie": relatie,
    }


def _fake_parse(families):
    def _inner(content):
        return families, {}, [], []

    return _inner


def _upload(db, *, name="ledenrapport.xls", content=b"binary") -> dict:
    file = UploadFile(io.BytesIO(content), filename=name)
    return asyncio.run(import_preview(db, file, admin=seeded_admin(db)))


def _commit(db, token: str) -> dict:
    return import_commit(db, token, admin=seeded_admin(db))


def _refusal(call) -> int:
    with pytest.raises(HTTPException) as refused:
        call()
    return refused.value.status_code


def test_the_import_screen_asks_a_session(client, db_session):
    """Without a session neither step of the import screen does anything. The two
    JSON routes each refused a visitor; the screen's routes are what is left."""
    client.cookies.clear()
    preview = client.post(
        "/admin/leden-import/preview",
        files={"file": ("ledenrapport.xls", b"binary", "application/vnd.ms-excel")},
        follow_redirects=False,
    )
    commit = client.post("/admin/leden-import/commit", data={"token": "x"}, follow_redirects=False)
    assert preview.status_code in (303, 403) and commit.status_code in (303, 403)
    assert mi._PENDING == {} and db_session.query(Member).count() == 0


def test_preview_then_commit_applies(db_session, monkeypatch):
    seed_postal_code(db_session)
    families = [[_row("100", "Jan", "Janssens", email="jan@example.com")]]
    monkeypatch.setattr(mi, "parse_families", _fake_parse(families))

    body = _upload(db_session)
    assert body["report"]["new_families"] == 1
    assert body["selected_families"] == 1
    token = body["token"]
    # Dry-run: nog niets weggeschreven.
    assert db_session.query(Member).count() == 0

    assert _commit(db_session, token)["report"]["new_families"] == 1
    assert db_session.query(Member).count() == 1


def test_commit_unknown_token_404(db_session):
    assert _refusal(lambda: _commit(db_session, "bestaat-niet")) == 404


def test_commit_expired_token_410(db_session, monkeypatch):
    families = [[_row("100", "Jan", "Janssens")]]
    monkeypatch.setattr(mi, "parse_families", _fake_parse(families))
    seed_postal_code(db_session)

    token = _upload(db_session)["token"]
    # Forceer verloop: zet de aanmaaktijd ver in het verleden.
    mi._PENDING[token]["created_at"] -= mi._TTL_SECONDS + 1

    assert _refusal(lambda: _commit(db_session, token)) == 410


def test_token_single_use(db_session, monkeypatch):
    families = [[_row("100", "Jan", "Janssens")]]
    monkeypatch.setattr(mi, "parse_families", _fake_parse(families))
    seed_postal_code(db_session)

    token = _upload(db_session)["token"]
    assert _commit(db_session, token)["report"]["new_families"] == 1
    # Tweede keer: token is verbruikt.
    assert _refusal(lambda: _commit(db_session, token)) == 404


def test_preview_invalid_file_400(db_session):
    assert _refusal(lambda: _upload(db_session, content=b"dit is geen excel")) == 400


def test_preview_xlsx_rejected(db_session):
    assert _refusal(lambda: _upload(db_session, name="ledenrapport.xlsx")) == 400


def test_preview_empty_file_400(db_session):
    assert _refusal(lambda: _upload(db_session, content=b"")) == 400
