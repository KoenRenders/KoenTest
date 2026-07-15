"""Admin-upload van affiche/reglement: een geweigerd bestand (verkeerd type) mag
niet stil mislukken — htmx swapt niet op een 4xx, dus de route moet de fout
opvangen en tonen (met een hint over toegelaten types). Reproductie van de bug
waarbij een upload 'niet lukte' zonder feedback (o.a. iPhone-HEIC)."""
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value

_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_reglement_bad_type_shows_error_not_silent(client, db_session):
    _a, comp, _p = seed_activity_with_product(db_session)
    csrf = _login(client)
    resp = client.post(
        f"/admin/activiteiten/{comp.activity_id}/onderdelen/{comp.id}/reglement",
        files={"file": ("foto.heic", b"nonsense", "image/heic")},
        headers={"X-CSRF-Token": csrf})
    # De route vangt de 400 en re-rendert het detail (200) mét foutmelding.
    assert resp.status_code == 200
    assert "bestandstype" in resp.text.lower()
    assert "HEIC" in resp.text or "PDF" in resp.text


def test_reglement_valid_pdf_succeeds(client, db_session):
    _a, comp, _p = seed_activity_with_product(db_session)
    csrf = _login(client)
    resp = client.post(
        f"/admin/activiteiten/{comp.activity_id}/onderdelen/{comp.id}/reglement",
        files={"file": ("reglement.pdf", _PDF, "application/pdf")},
        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert "bestandstype" not in resp.text.lower()
    db_session.expire_all()
    from app.domains.activities.api import ActivitySubRegistration
    c = db_session.get(ActivitySubRegistration, comp.id)
    assert c.info_asset_url is not None
