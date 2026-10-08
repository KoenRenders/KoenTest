"""#670 — het aantal wijzigen laat het totaal meteen meelopen.

**#1287, 29 September 2026: no line amount any more.** #670 showed one per row
next to the total; Koen decided the line amount goes everywhere, as on the
registration form ("doe het er in de backoffice dan ook maar af"). The total still
follows a changed quantity at once, and the first test now also holds that the
line amount stays gone. The history below is #670's.

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
from tests.conftest import SEEDED_ADMIN_EMAIL, register_at_the_door, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _inschrijving(client, db, aantal=2):
    activity, comp, product = seed_activity_with_product(db, price="10.00")
    resp = register_at_the_door(
        client,
        activity.id,
        json={
            "contact_name": "An Janssens",
            "phone": "0470000000",
            "contact_email": "an@example.com",
            "component_id": comp.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": aantal}],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    reg_id = resp.json()["id"]
    from app.domains.activities.api import Registration

    reg = db.query(Registration).filter(Registration.id == reg_id).one()
    return reg, reg.items[0]


def test_een_hoger_aantal_toont_meteen_het_nieuwe_bedrag(client, db_session):
    reg, item = _inschrijving(client, db_session, aantal=2)
    csrf = _login(client)

    r = client.post(
        f"/admin/inschrijvingen/{reg.id}/totaal",
        data={f"product_{item.product_id}": "5"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    # Het totaal: 5 x 10,00 — en alleen het totaal (#1287): geen regelbedrag.
    assert "50,00" in r.text, "het totaal loopt niet mee"
    # #1613: the answer IS the total and nothing else — once, no product row
    # (so no line amount, #1287) and no field that could put typed text back.
    assert r.text.count("50,00") == 1 and r.text.count("Totaal") == 1, r.text
    assert "data-product-row" not in r.text and "<input" not in r.text


def test_de_herberekening_bewaart_niets(client, db_session):
    """De invariant die #613-2 beschermt."""
    reg, item = _inschrijving(client, db_session, aantal=2)
    csrf = _login(client)

    client.post(
        f"/admin/inschrijvingen/{reg.id}/totaal",
        data={f"product_{item.product_id}": "9"},
        headers={"X-CSRF-Token": csrf},
    )

    db_session.expire_all()
    from app.domains.activities.api import RegistrationItem

    bewaard = db_session.get(RegistrationItem, item.id)
    assert bewaard.quantity == 2, (
        "het live-endpoint heeft opgeslagen — de autosave van #613-2 is via de achterdeur terug"
    )


def test_zonder_aantallen_toont_het_de_bewaarde_stand(client, db_session):
    reg, item = _inschrijving(client, db_session, aantal=3)
    csrf = _login(client)

    r = client.post(
        f"/admin/inschrijvingen/{reg.id}/totaal", data={}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 200 and "30,00" in r.text


def test_het_endpoint_vereist_een_beheerder(client, db_session):
    """Eigen endpoint met require_admin_ui + CSRF; het publieke /totaal is open."""
    reg, item = _inschrijving(client, db_session)
    r = client.post(
        f"/admin/inschrijvingen/{reg.id}/totaal", data={f"product_{item.product_id}": "5"}
    )
    assert r.status_code in (401, 403)


def test_de_rekenkant_blijft_die_van_totals_py(client, db_session):
    """Geen tweede berekening in de UI-module (§19.3)."""
    from app.domains.activities.api import quote_registration

    reg, item = _inschrijving(client, db_session, aantal=2)
    totaal, regels = quote_registration(reg, {item.id: 5})
    assert totaal == Decimal("50.00")
    assert regels[0]["quantity"] == 5 and regels[0]["subtotal"] == Decimal("50.00")

    bron = open("app/domains/activities/admin_ui.py", encoding="utf-8").read()
    stuk = bron[bron.index("async def inschrijving_totaal(") :]
    stuk = stuk[: stuk.index("@router.post")]
    assert "unit_price" not in stuk and "member_price" not in stuk, (
        "er wordt in de UI-module zelf gerekend"
    )


def test_de_producten_staan_boven_de_opmerking_in_een_formulier(client, db_session):
    """Consistent met het publieke formulier: de productrijen vóór de opmerking.

    #1494: er is geen "Product toevoegen" meer — elk product van het onderdeel
    staat als teller op de fiche. "Toevoegen zonder keuze" bestaat dus ook niet.
    """
    reg, _item = _inschrijving(client, db_session)
    _login(client)

    html = client.get(f"/admin/inschrijvingen/{reg.id}").text
    assert "Product toevoegen" not in html and 'name="product_id"' not in html
    assert "data-product-row" in html and "Opmerking" in html
    assert html.index("data-product-row") < html.index("Opmerking")
    # Eén formulier: de opmerking mag niet losgeknipt worden van de aantallen (#613-2).
    assert html.count("<form") == 1, (
        f"{html.count('<form')} formulieren — de ene Opslaan is opgesplitst"
    )
