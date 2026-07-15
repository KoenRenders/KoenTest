"""Een per-onderdeel geüpload info/reglement-document verschijnt als 'Info ↗'-link
op de publieke activiteitenkaart (rechts van Inschrijven / Wie doet er mee) — #476.
Bewijst de volledige keten: admin-upload → info_asset_url → publieke weergave."""
from tests.conftest import seed_activity_with_product

_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


def test_uploaded_component_info_shows_as_info_link_on_card(client, db_session, admin_headers):
    _activity, comp, _p = seed_activity_with_product(db_session)
    # Admin uploadt een info/reglement-document bij het onderdeel.
    resp = client.post(f"/api/v1/admin/components/{comp.id}/info",
                       files={"file": ("reglement.pdf", _PDF, "application/pdf")},
                       headers=admin_headers)
    assert resp.status_code == 200, resp.text
    media_url = resp.json()["url"]  # /api/v1/media/<id>

    # Publieke kaart toont nu de 'Info'-link naar dat document.
    html = client.get("/activiteiten").text
    assert media_url in html
    assert "Info" in html


def test_no_info_link_without_document(client, db_session):
    seed_activity_with_product(db_session)
    html = client.get("/activiteiten").text
    # Zonder info-document en zonder info_url geen 'Info ↗'-link.
    assert "Info ↗" not in html
