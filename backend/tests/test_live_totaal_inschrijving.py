"""#670 — het aantal wijzigen laat regelbedrag én totaal meteen meelopen.

Op het beheerpaneel bleef alles staan tot je opsloeg. Koen wil het zien "zoals
wanneer een bezoeker bestelt". Alleen het totaal verversen zou "€ 20,00" naast een
aantal van 3 laten staan — verwarrender dan niets doen; dus beide.

De rekenkant was al gedeeld: `totals.py` is de enige bron voor "wat kost deze
inschrijving". Wat ontbrak was het live-mechanisme, en dat vroeg één ontwerpkeuze —
zie de docstring van `quote_registration`.

**De herberekening bewaart niets.** Er is bewust één "Opslaan" voor aantallen én
opmerking (#613-2); de autosave-op-change is daar destijds uitgehaald. Een
live-endpoint dat stilletjes opslaat brengt die via de achterdeur terug.
"""
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _inschrijving(client, db, aantal=2):
    activity, comp, product = seed_activity_with_product(db, price="10.00")
    resp = client.post(f"/api/v1/activities/{activity.id}/register", json={
        "contact_name": "An Janssens", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": aantal}]})
    assert resp.status_code in (200, 201), resp.text
    reg_id = resp.json()["id"]
    from app.domains.activities.api import Registration
    reg = db.query(Registration).filter(Registration.id == reg_id).one()
    return reg, reg.items[0]


def test_een_hoger_aantal_toont_meteen_het_nieuwe_bedrag(client, db_session):
    reg, item = _inschrijving(client, db_session, aantal=2)
    csrf = _login(client)

    r = client.post(f"/admin/inschrijvingen/{reg.id}/totaal",
                    data={f"quantity_{item.id}": "5"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    # Regelbedrag én totaal: 5 x 10,00.
    assert "50.00" in r.text, "het totaal loopt niet mee"
    assert r.text.count("50.00") >= 2, (
        "alleen het totaal is bijgewerkt; het regelbedrag hoort ook mee te lopen")


def test_de_herberekening_bewaart_niets(client, db_session):
    """De invariant die #613-2 beschermt."""
    reg, item = _inschrijving(client, db_session, aantal=2)
    csrf = _login(client)

    client.post(f"/admin/inschrijvingen/{reg.id}/totaal",
                data={f"quantity_{item.id}": "9"},
                headers={"X-CSRF-Token": csrf})

    db_session.expire_all()
    from app.domains.activities.api import RegistrationItem
    bewaard = db_session.get(RegistrationItem, item.id)
    assert bewaard.quantity == 2, (
        "het live-endpoint heeft opgeslagen — de autosave van #613-2 is via de "
        "achterdeur terug")


def test_zonder_aantallen_toont_het_de_bewaarde_stand(client, db_session):
    reg, item = _inschrijving(client, db_session, aantal=3)
    csrf = _login(client)

    r = client.post(f"/admin/inschrijvingen/{reg.id}/totaal", data={},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and "30.00" in r.text


def test_het_endpoint_vereist_een_beheerder(client, db_session):
    """Eigen endpoint met require_admin_ui + CSRF; het publieke /totaal is open."""
    reg, item = _inschrijving(client, db_session)
    r = client.post(f"/admin/inschrijvingen/{reg.id}/totaal",
                    data={f"quantity_{item.id}": "5"})
    assert r.status_code in (401, 403)


def test_de_rekenkant_blijft_die_van_totals_py(client, db_session):
    """Geen tweede berekening in de UI-module (§19.3)."""
    from app.domains.activities.api import quote_registration

    reg, item = _inschrijving(client, db_session, aantal=2)
    totaal, regels = quote_registration(reg, {item.id: 5})
    assert totaal == Decimal("50.00")
    assert regels[0]["quantity"] == 5 and regels[0]["subtotal"] == Decimal("50.00")

    bron = open("app/domains/activities/admin_ui.py", encoding="utf-8").read()
    stuk = bron[bron.index("async def inschrijving_totaal("):]
    stuk = stuk[:stuk.index("@router.post")]
    assert "unit_price" not in stuk and "member_price" not in stuk, (
        "er wordt in de UI-module zelf gerekend")


def test_product_toevoegen_staat_boven_de_opmerking(client, db_session):
    """Consistent met het publieke formulier; het stond ná de Opslaan-knop."""
    reg, _item = _inschrijving(client, db_session)
    _login(client)

    html = client.get(f"/admin/inschrijvingen/{reg.id}").text
    assert "Product toevoegen" in html and "Opmerking" in html
    assert html.index("Product toevoegen") < html.index("Opmerking"), (
        "Product toevoegen staat nog onder de opmerking")
    # Eén formulier: de opmerking mag niet losgeknipt worden van de aantallen (#613-2).
    assert html.count("<form") == 1, (
        f"{html.count('<form')} formulieren — de ene Opslaan is opgesplitst")


def test_toevoegen_zonder_keuze_geeft_een_melding(client, db_session):
    """De keuzelijst kan geen `required` dragen zonder ook Opslaan te blokkeren."""
    reg, _item = _inschrijving(client, db_session)
    csrf = _login(client)

    r = client.post(f"/admin/inschrijvingen/{reg.id}/regels",
                    data={"product_id": "", "quantity": "1"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and "Kies eerst een product" in r.text
