"""Auditdekking activiteiten-domein (#189): de uniforme wijzigingenfeed toont wat
het activiteitenbeheer schrijft. Dat elke bewaaractie van de fiche haar history-rij
schrijft, staat bij de fiche zelf (`test_fiche_save.py`,
`test_new_activity_on_fiche_1649.py`)."""

from datetime import date

from app.domains.activities import service
from tests import backoffice_door
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product


def test_unified_changes_feed(client, db_session, admin_headers):
    """#189: de uniforme feed bevat activiteit-wijzigingen, met een werkende
    objectgroep-filter."""
    activity, _component, _product = seed_activity_with_product(db_session)
    service.update_activity(db_session, activity.id, {"name": "Feeddag"}, actor=SEEDED_ADMIN_EMAIL)
    since = date.today().isoformat()

    r = backoffice_door.changes(client, since)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Activiteiten" in body["groups"]
    assert any(
        row["group"] == "Activiteiten" and row["entity"] == "Activiteit" for row in body["rows"]
    )

    r2 = backoffice_door.changes(client, since, group="Activiteiten")
    rows2 = r2.json()["rows"]
    assert rows2 and all(row["group"] == "Activiteiten" for row in rows2)
