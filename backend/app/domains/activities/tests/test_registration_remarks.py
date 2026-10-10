"""Het beheer bewerkt de opmerking van de inschrijver (#283): zetten/wijzigen/
wissen (→ NULL), soft-deleted niet bewerkbaar, en bestelregels/saldo blijven
ongemoeid. Sinds CR-13 fase 4b (#1251) aan de service gemeten — de JSON-route die
ze doorgaf is weg; het scherm roept dezelfde functie aan."""

from app.domains.activities import service as activities_service
from app.domains.activities.api import Registration
from app.soft_delete import soft_delete
from tests.conftest import SEEDED_ADMIN_EMAIL, register_at_the_door, seed_activity_with_product


def _register(client, activity_id, comp, product, remarks=None, email="an@example.com"):
    payload = {
        "contact_name": "An Janssens",
        "phone": "0470000000",
        "contact_email": email,
        "component_id": comp.id,
        "payment_method": "transfer",
        "items": [{"product_id": product.id, "quantity": 2}],
    }
    if remarks is not None:
        payload["remarks"] = remarks
    resp = register_at_the_door(client, activity_id, json=payload)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _remark(db, activity_id, reg_id, text):
    return activities_service.update_registration_contact(
        db, activity_id, reg_id, {"remarks": text}, actor=SEEDED_ADMIN_EMAIL
    )


def test_admin_can_set_change_and_clear_remarks(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    reg_id = _register(client, activity_id, comp, product)

    # Zetten
    assert _remark(db_session, activity_id, reg_id, "Komt iets later").remarks == "Komt iets later"

    # Wijzigen
    assert _remark(db_session, activity_id, reg_id, "Toch op tijd").remarks == "Toch op tijd"

    # Wissen: enkel witruimte wordt genormaliseerd naar NULL
    assert _remark(db_session, activity_id, reg_id, "   ").remarks is None
    db_session.expire_all()
    assert db_session.get(Registration, reg_id).remarks is None


def test_remarks_update_leaves_order_lines_untouched(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    reg_id = _register(client, activity_id, comp, product)

    reg = _remark(db_session, activity_id, reg_id, "notitie")
    db_session.expire_all()
    # Bestelregel blijft ongemoeid: nog steeds één regel met aantal 2.
    assert len(reg.items) == 1
    assert reg.items[0].quantity == 2


def test_registration_list_order_stable_after_remark_edit(client, db_session):
    """#285: de lijst is stabiel gesorteerd (oud → nieuw); een bewerkte opmerking
    laat de inschrijving NIET naar onderen springen."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    ids = [
        _register(client, activity_id, comp, product, email=f"reg{i}@example.com") for i in range(3)
    ]

    def _order():
        return [r["id"] for r in activities_service.registrations_for(db_session, activity_id)]

    before = _order()
    assert before == ids  # oud → nieuw (aanmaakvolgorde)

    # Bewerk de opmerking van de EERSTE inschrijving.
    assert _remark(db_session, activity_id, ids[0], "gewijzigd") is not None

    assert _order() == before  # volgorde ongewijzigd — niet naar onderen gesprongen


def test_remarks_update_on_soft_deleted_is_not_found(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    reg_id = _register(client, activity_id, comp, product)

    reg = db_session.get(Registration, reg_id)
    soft_delete(reg)
    db_session.commit()

    assert _remark(db_session, activity_id, reg_id, "mag niet") is None
