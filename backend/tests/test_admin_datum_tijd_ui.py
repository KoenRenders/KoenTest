"""Activiteiten-admin: datum met begin-/einduur toevoegen én een bestaande
datum (incl. uren) bewerken (#451/#454, v1.14-pariteit). Sessie + CSRF vereist."""
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.activities.api import ActivityDate


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_datum_toevoegen_met_uren(client, db_session):
    activity, _comp, _p = seed_activity_with_product(db_session)
    csrf = _login(client)
    r = client.post(f"/admin/activiteiten/{activity.id}/datums",
                    data={"start_date": "2031-09-01", "start_time": "19:30",
                          "end_time": "22:00"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and "19:30" in r.text and "22:00" in r.text
    db_session.expire_all()
    ad = (db_session.query(ActivityDate)
          .filter(ActivityDate.activity_id == activity.id,
                  ActivityDate.start_date == __import__("datetime").date(2031, 9, 1))
          .one())
    assert ad.start_time.strftime("%H:%M") == "19:30"
    assert ad.end_time.strftime("%H:%M") == "22:00"


def test_bestaande_datum_bewerken(client, db_session):
    activity, _comp, _p = seed_activity_with_product(db_session)
    csrf = _login(client)
    # de fixture heeft één datum zonder uren
    db_session.expire_all()
    ad = db_session.query(ActivityDate).filter(
        ActivityDate.activity_id == activity.id).first()
    r = client.post(f"/admin/activiteiten/{activity.id}/datums/{ad.id}",
                    data={"start_date": "2032-01-15", "start_time": "10:00"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and "10:00" in r.text
    db_session.expire_all()
    ad2 = db_session.get(ActivityDate, ad.id)
    assert ad2.start_date.strftime("%Y-%m-%d") == "2032-01-15"
    assert ad2.start_time.strftime("%H:%M") == "10:00"


def test_datum_bewerken_vereist_csrf(client, db_session):
    activity, _comp, _p = seed_activity_with_product(db_session)
    _login(client)
    ad = db_session.query(ActivityDate).filter(
        ActivityDate.activity_id == activity.id).first()
    r = client.post(f"/admin/activiteiten/{activity.id}/datums/{ad.id}",
                    data={"start_date": "2032-02-02"})
    assert r.status_code == 403
