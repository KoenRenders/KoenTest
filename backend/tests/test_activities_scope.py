"""Eén /activities-endpoint met scope-param (#136): upcoming/archived/all.

Invariant: upcoming toont enkel activiteiten met een toekomstige datum, archived
enkel die met een voorbije datum, all toont beide. Default = upcoming.
"""
from datetime import date, timedelta


def _make_activity(db, name, day_offset):
    from app.models.activity import Activity, ActivityDate
    a = Activity(name=name)
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=date.today() + timedelta(days=day_offset)))
    db.flush()
    return a


def test_scope_filters_upcoming_archived_all(client, db_session):
    _make_activity(db_session, "Toekomst", 10)
    _make_activity(db_session, "Verleden", -10)

    up = [a["name"] for a in client.get("/api/v1/activities?scope=upcoming").json()]
    assert "Toekomst" in up and "Verleden" not in up

    arch = [a["name"] for a in client.get("/api/v1/activities?scope=archived").json()]
    assert "Verleden" in arch and "Toekomst" not in arch

    allr = [a["name"] for a in client.get("/api/v1/activities?scope=all").json()]
    assert "Toekomst" in allr and "Verleden" in allr


def test_default_scope_is_upcoming(client, db_session):
    _make_activity(db_session, "DefaultToekomst", 10)
    _make_activity(db_session, "DefaultVerleden", -10)
    names = [a["name"] for a in client.get("/api/v1/activities").json()]
    assert "DefaultToekomst" in names
    assert "DefaultVerleden" not in names


def test_all_scope_orders_upcoming_first_soonest_top(client, db_session):
    """admin-sortering (#186): toekomstige activiteiten eerst, de snelst komende
    bovenaan; daarna de voorbije, meest recente eerst."""
    _make_activity(db_session, "VerVerleden", -30)
    _make_activity(db_session, "RecentVerleden", -5)
    _make_activity(db_session, "Binnenkort", 3)
    _make_activity(db_session, "VerToekomst", 30)

    names = [a["name"] for a in client.get("/api/v1/activities?scope=all").json()]
    assert names == ["Binnenkort", "VerToekomst", "RecentVerleden", "VerVerleden"]


def test_all_scope_activity_with_future_and_past_sorts_as_upcoming(client, db_session):
    """#186: een activiteit met zowel een voorbije als een toekomstige datum sorteert
    op haar eerstvolgende toekomstige datum (in de 'toekomstig eerst'-groep)."""
    from app.models.activity import Activity, ActivityDate
    a = Activity(name="Reeks")
    db_session.add(a)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=a.id, start_date=date.today() - timedelta(days=20)))
    db_session.add(ActivityDate(activity_id=a.id, start_date=date.today() + timedelta(days=5)))
    db_session.flush()
    _make_activity(db_session, "VerToekomst", 60)
    _make_activity(db_session, "Verleden", -3)

    names = [x["name"] for x in client.get("/api/v1/activities?scope=all").json()]
    assert names.index("Reeks") < names.index("VerToekomst")   # +5 vóór +60
    assert names.index("Reeks") < names.index("Verleden")      # toekomstig vóór voorbij
    assert names.index("VerToekomst") < names.index("Verleden")


def test_activity_response_exposes_is_cancelled(client, db_session):
    """Regressie (#257): de respons bevatte is_cancelled niet, dus de bewerk-vorm
    toonde het vinkje altijd 'uit' (leek niet opgeslagen). Nu wel teruggegeven."""
    from app.models.activity import Activity, ActivityDate
    a = Activity(name="Geannuleerd feest", is_cancelled=True)
    db_session.add(a)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=a.id, start_date=date.today() + timedelta(days=10)))
    db_session.flush()

    data = client.get("/api/v1/activities?scope=all").json()
    match = next((x for x in data if x["name"] == "Geannuleerd feest"), None)
    assert match is not None
    assert match["is_cancelled"] is True


def test_old_archived_endpoint_is_gone(client):
    """De aparte GET /activities/archived is weg (harde cut). Het pad matcht nu de
    /activities/{activity_id}-route zonder GET-handler → 405 (of 404); in elk geval
    geen geldige archieflijst (200)."""
    resp = client.get("/api/v1/activities/archived")
    assert resp.status_code in (404, 405)
