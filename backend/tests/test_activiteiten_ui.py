"""Fase 4a-3 (#402): publieke activiteiten server-rendered — lijst, archief,
registratieflow met server-side totaal en Mollie-redirect."""
from decimal import Decimal

from tests.conftest import seed_activity_with_product


def test_activiteiten_lijst_toont_activiteit(client, db_session):
    activity, component, product = seed_activity_with_product(db_session, price="10.00", is_free=False)
    resp = client.get("/activiteiten")
    assert resp.status_code == 200
    assert activity.name in resp.text and "Inschrijven" in resp.text


def test_archief_page_renders(client, db_session):
    assert client.get("/activiteiten/archief").status_code == 200


def test_inschrijf_form_en_serverside_totaal(client, db_session):
    activity, component, product = seed_activity_with_product(db_session, price="10.00", is_free=False)
    form = client.get(f"/activiteiten/{activity.id}/inschrijven/{component.id}")
    assert form.status_code == 200 and "E-mailadres" in form.text

    totaal = client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}/totaal",
                         data={f"product_{product.id}": "3"})
    assert totaal.status_code == 200 and "30.00" in totaal.text


def test_inschrijven_gratis_zonder_checkout(client, db_session):
    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
    resp = client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}",
                       data={"contact_name": "Fee", "contact_email": "fee@example.com",
                             "phone": "0470000000", f"product_{product.id}": "1"})
    assert resp.status_code == 200 and "Bedankt, Fee" in resp.text
    assert "HX-Redirect" not in resp.headers

    from app.domains.activities.api import Registration
    reg = db_session.query(Registration).order_by(Registration.id.desc()).first()
    assert reg.contact_name == "Fee" and reg.component_id == component.id


def test_inschrijven_online_redirect_naar_mollie(client, db_session, mock_mollie):
    activity, component, product = seed_activity_with_product(db_session, price="12.50", is_free=False)
    resp = client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}",
                       data={"contact_name": "Roos", "contact_email": "roos@example.com",
                             "phone": "0470000001", f"product_{product.id}": "1",
                             "payment_method": "ONLINE"})
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect", "").startswith("https://mollie.test/checkout/")


def test_inschrijven_validatiefouten(client, db_session):
    activity, component, product = seed_activity_with_product(db_session, price="10.00", is_free=False)
    resp = client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}",
                       data={"contact_name": "", "contact_email": "x", "phone": ""})
    assert resp.status_code == 200 and "Vul naam, e-mailadres en mobiel nummer in" in resp.text

    resp2 = client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}",
                        data={"contact_name": "A", "contact_email": "a@example.com",
                              "phone": "047", f"product_{product.id}": "0"})
    assert "Selecteer minstens één product" in resp2.text
