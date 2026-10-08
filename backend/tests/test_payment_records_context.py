"""Penningmeester-filter (#90): de records-lijst geeft genoeg context mee om per
lidmaatschap-vernieuwing of per activiteit-onderdeel te filteren."""

from tests import payments_door
from tests.conftest import register_at_the_door, seed_activity_with_product


def test_registration_record_exposes_component(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    resp = register_at_the_door(
        client,
        activity_id,
        json={
            "contact_name": "An",
            "phone": "0470000000",
            "contact_email": "an@example.com",
            "component_id": comp.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": 1}],
        },
    )
    assert resp.status_code in (200, 201), resp.text

    records = payments_door.records(client).json()
    reg_rec = next(r for r in records if r["payable_type"] == "registration")
    # #1748: the record no longer carries `activity_id` — its one reader, the jump
    # link on the booking's page, follows the describer's `context_href` now.
    assert reg_rec["context_href"] == f"/admin/activiteiten/{activity_id}"
    assert reg_rec["component_id"] == comp.id
    assert reg_rec["component_name"] == comp.name


def test_registration_record_exposes_structured_communication(client, db_session, admin_headers):
    """De OGM van een overschrijving staat in de betalingenlijst, zodat de
    penningmeester ze kan gebruiken om manueel af te boeken (#224)."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    resp = register_at_the_door(
        client,
        comp.activity_id,
        json={
            "contact_name": "An",
            "phone": "0470000000",
            "contact_email": "an@example.com",
            "component_id": comp.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": 1}],
        },
    )
    assert resp.status_code in (200, 201), resp.text

    records = payments_door.records(client).json()
    reg_rec = next(r for r in records if r["payable_type"] == "registration")
    assert reg_rec["structured_communication"]
    assert reg_rec["structured_communication"].startswith("+++")
