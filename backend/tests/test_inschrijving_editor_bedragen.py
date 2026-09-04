"""Inschrijvingsdetail: werkende attributen, één "Opslaan", bedragen (#613/#616/#617).

Drie dingen die op HDEV stuk waren en die je aan de serverkant niet ziet: de
attributen werden ge-escaped (htmx deed niets), aantal en opmerking sloegen apart op,
en het paneel toonde geen bedragen. De regressietest op de escaping is hier de
belangrijkste — dit is de derde keer dat die klasse fout opduikt (#514, #613, #616).
"""

import pytest
pytestmark = pytest.mark.ui_serverrendered
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.activities.api import Registration, RegistrationItem


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _inschrijving(client, db):
    activity, comp, product = seed_activity_with_product(db, is_free=False)
    resp = client.post(f"/api/v1/activities/{activity.id}/register", json={
        "contact_name": "An Janssens", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    assert resp.status_code in (200, 201), resp.text
    reg_id = resp.json()["id"]
    item_id = db.query(RegistrationItem).filter(
        RegistrationItem.registration_id == reg_id).first().id
    return reg_id, item_id


def test_attributen_zijn_niet_geescaped(client, db_session):
    """De kern van #613: `hx-target=&#34;…&#34;` maakt htmx blind voor het doel."""
    reg_id, _ = _inschrijving(client, db_session)
    _login(client)
    html = client.get(f"/admin/inschrijvingen/{reg_id}").text

    assert "hx-target=&#34;" not in html and "hx-swap=&#34;" not in html
    assert 'hx-target="closest .bg-gray-50"' in html
    assert 'hx-swap="outerHTML"' in html


def test_een_opslaan_voor_aantallen_en_opmerking(client, db_session):
    """#613-2: geen autosave op change, geen aparte "Opmerking opslaan" meer."""
    reg_id, item_id = _inschrijving(client, db_session)
    _login(client)
    html = client.get(f"/admin/inschrijvingen/{reg_id}").text

    assert 'hx-trigger="change"' not in html
    assert "Opmerking opslaan" not in html
    assert f'hx-post="/admin/inschrijvingen/{reg_id}/opslaan"' in html
    assert f'name="quantity_{item_id}"' in html


def test_opslaan_bewaart_aantal_en_opmerking_samen(client, db_session):
    reg_id, item_id = _inschrijving(client, db_session)
    csrf = _login(client)

    r = client.post(f"/admin/inschrijvingen/{reg_id}/opslaan",
                    data={f"quantity_{item_id}": "3", "remarks": "Nota van de admin"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text

    db_session.expire_all()
    assert db_session.get(RegistrationItem, item_id).quantity == 3
    assert db_session.get(Registration, reg_id).remarks == "Nota van de admin"


def test_paneel_blijft_open_en_ververst_de_kaart(client, db_session):
    """#613-3 en #613-4/#617-3: niet terugvallen in lees-modus, en de kaart erboven —
    die buiten dit fragment staat — mee laten verversen."""
    reg_id, item_id = _inschrijving(client, db_session)
    csrf = _login(client)

    r = client.post(f"/admin/inschrijvingen/{reg_id}/opslaan",
                    data={f"quantity_{item_id}": "2", "remarks": ""},
                    headers={"X-CSRF-Token": csrf})
    assert "{ edit: true }" in r.text
    assert r.headers.get("HX-Trigger") == "betalingen-ververst"


def test_paneel_toont_bedragen_en_totaal(client, db_session):
    """#613-4: zonder bedragen zie je niet wát je aan het wijzigen bent. Het bedrag
    komt uit compute_registration_total, dezelfde bron als de betaalrecords."""
    reg_id, item_id = _inschrijving(client, db_session)
    csrf = _login(client)
    client.post(f"/admin/inschrijvingen/{reg_id}/opslaan",
                data={f"quantity_{item_id}": "2", "remarks": ""},
                headers={"X-CSRF-Token": csrf})

    html = client.get(f"/admin/inschrijvingen/{reg_id}").text
    from app.domains.activities.api import compute_registration_total
    db_session.expire_all()
    totaal, _regels = compute_registration_total(db_session.get(Registration, reg_id))
    assert "Totaal" in html
    assert f'€ {totaal:.2f}' in html
