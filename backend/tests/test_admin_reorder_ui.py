"""Activiteiten-admin: onderdelen en producten herordenen via sort_order-wissel
(#451/#454). De helper normaliseert eerst naar 0..n (ook als alles nog default 0
is) en wisselt dan met de buur; buiten bereik = no-op. Sessie + CSRF vereist."""
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.activities.api import Activity, ActivitySubRegistration


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _components_in_order(db, activity_id):
    activity = db.query(Activity).filter(Activity.id == activity_id).one()
    return [c.name for c in sorted(activity.sub_registrations,
                                   key=lambda s: (s.sort_order or 0, s.id))]


def test_onderdeel_omlaag_en_omhoog(client, db_session):
    activity, comp, _p = seed_activity_with_product(db_session)  # "Onderdeel"
    csrf = _login(client)
    # tweede onderdeel toevoegen
    client.post(f"/admin/activiteiten/{activity.id}/onderdelen",
                data={"name": "Tweede"}, headers={"X-CSRF-Token": csrf})
    db_session.expire_all()
    assert _components_in_order(db_session, activity.id) == ["Onderdeel", "Tweede"]

    # eerste onderdeel omlaag → volgorde keert om
    r = client.post(f"/admin/activiteiten/{activity.id}/onderdelen/{comp.id}/verplaats",
                    data={"richting": "omlaag"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    db_session.expire_all()
    assert _components_in_order(db_session, activity.id) == ["Tweede", "Onderdeel"]

    # weer omhoog → oorspronkelijke volgorde
    client.post(f"/admin/activiteiten/{activity.id}/onderdelen/{comp.id}/verplaats",
                data={"richting": "omhoog"}, headers={"X-CSRF-Token": csrf})
    db_session.expire_all()
    assert _components_in_order(db_session, activity.id) == ["Onderdeel", "Tweede"]


def test_onderdeel_omhoog_aan_de_top_is_noop(client, db_session):
    activity, comp, _p = seed_activity_with_product(db_session)
    csrf = _login(client)
    client.post(f"/admin/activiteiten/{activity.id}/onderdelen",
                data={"name": "Tweede"}, headers={"X-CSRF-Token": csrf})
    # het eerste onderdeel kan niet hoger
    r = client.post(f"/admin/activiteiten/{activity.id}/onderdelen/{comp.id}/verplaats",
                    data={"richting": "omhoog"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    db_session.expire_all()
    assert _components_in_order(db_session, activity.id)[0] == "Onderdeel"


def test_verplaats_vereist_csrf(client, db_session):
    activity, comp, _p = seed_activity_with_product(db_session)
    _login(client)
    r = client.post(f"/admin/activiteiten/{activity.id}/onderdelen/{comp.id}/verplaats",
                    data={"richting": "omlaag"})
    assert r.status_code == 403
