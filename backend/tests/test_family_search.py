"""Zoek + paginatie op de Admin-ledenlijst (#233).

De lijst is server-side gepagineerd; zonder server-side zoeken zijn leden buiten
de huidige pagina niet vindbaar. De zoekterm matcht op voor-/achternaam, volledige
naam of e-mail van een gezinslid.
"""
from tests.conftest import seed_postal_code


def _make_family(client, last, first, email, mobile, *, street="Milostraat", nr="40"):
    resp = client.post("/api/v1/families", json={
        "street": street, "house_number": nr, "postal_code": "2400",
        "payment_method": "transfer",
        "members": [{"last_name": last, "first_name": first, "email": email,
                     "mobile": mobile, "relation_type": "HOOFDLID"}],
    })
    assert resp.status_code == 201, resp.text


def test_families_search_by_name_full_name_and_email(client, db_session, admin_headers):
    seed_postal_code(db_session)
    _make_family(client, "Renders", "Koen", "koen.renders@example.com", "0470111111")
    _make_family(client, "Peeters", "An", "an.peeters@example.com", "0470222222",
                 street="Kerkstraat", nr="1")

    def _names(body):
        return [m["last_name"] for fam in body["items"] for m in fam["members"]]

    # Achternaam (deelmatch, hoofdletterongevoelig).
    r = client.get("/api/v1/families", params={"q": "render"}, headers=admin_headers).json()
    assert r["total"] == 1 and "Renders" in _names(r) and "Peeters" not in _names(r)

    # Volledige naam.
    r2 = client.get("/api/v1/families", params={"q": "Koen Renders"}, headers=admin_headers).json()
    assert r2["total"] == 1 and "Renders" in _names(r2)

    # E-mail.
    r3 = client.get("/api/v1/families", params={"q": "an.peeters@example"}, headers=admin_headers).json()
    assert r3["total"] == 1 and "Peeters" in _names(r3)

    # Lege zoekterm → beide gezinnen.
    r4 = client.get("/api/v1/families", headers=admin_headers).json()
    assert r4["total"] == 2


def test_families_pagination_caps_and_counts(client, db_session, admin_headers):
    seed_postal_code(db_session)
    for i in range(3):
        _make_family(client, f"Lid{i}", "Test", f"lid{i}@example.com", f"04700000{i}{i}",
                     street="Teststraat", nr=str(i))

    r = client.get("/api/v1/families", params={"page": 1, "page_size": 2}, headers=admin_headers).json()
    assert r["total"] == 3
    assert r["total_pages"] == 2
    assert len(r["items"]) == 2

    r2 = client.get("/api/v1/families", params={"page": 2, "page_size": 2}, headers=admin_headers).json()
    assert len(r2["items"]) == 1
