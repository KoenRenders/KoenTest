"""Auditdekking activiteiten-domein (#189): create/update/delete van
activiteit/onderdeel/product schrijft een history-rij (incl. soft-delete)."""
from app.models.history import ActivityHistory, ComponentHistory, ProductHistory


def test_activity_domain_changes_are_audited(client, db_session, admin_headers):
    act = client.post("/api/v1/activities", headers=admin_headers, json={
        "name": "Auditdag", "dates": [{"start_date": "2099-12-31"}], "location": "X",
    })
    assert act.status_code == 200, act.text
    aid = act.json()["id"]
    assert db_session.query(ActivityHistory).filter(
        ActivityHistory.activity_id == aid, ActivityHistory.operation == "insert").count() == 1

    client.put(f"/api/v1/activities/{aid}", headers=admin_headers, json={"name": "Auditdag 2"})
    assert db_session.query(ActivityHistory).filter(
        ActivityHistory.activity_id == aid, ActivityHistory.operation == "update").count() >= 1

    comp = client.post(f"/api/v1/activities/{aid}/components", headers=admin_headers,
                       json={"name": "BBQ"})
    cid = comp.json()["id"]
    prod = client.post(f"/api/v1/activities/{aid}/components/{cid}/products",
                       headers=admin_headers, json={"name": "Vlees", "price": "5.00", "is_free": False})
    pid = prod.json()["id"]
    assert db_session.query(ComponentHistory).filter(
        ComponentHistory.component_id == cid, ComponentHistory.operation == "insert").count() == 1
    assert db_session.query(ProductHistory).filter(
        ProductHistory.product_id == pid, ProductHistory.operation == "insert").count() == 1

    # Soft-delete het product → delete-rij.
    client.delete(f"/api/v1/activities/{aid}/components/{cid}/products/{pid}", headers=admin_headers)
    assert db_session.query(ProductHistory).filter(
        ProductHistory.product_id == pid, ProductHistory.operation == "delete").count() == 1

    # Verwijder de hele activiteit → delete-rijen voor activiteit + onderdeel.
    client.delete(f"/api/v1/activities/{aid}", headers=admin_headers)
    assert db_session.query(ActivityHistory).filter(
        ActivityHistory.activity_id == aid, ActivityHistory.operation == "delete").count() == 1
    assert db_session.query(ComponentHistory).filter(
        ComponentHistory.component_id == cid, ComponentHistory.operation == "delete").count() == 1
