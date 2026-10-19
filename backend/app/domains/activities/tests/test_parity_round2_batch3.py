"""Ronde 2 (#476), derde lichting: jaargroepering op de activiteitenlijst +
bewerkbaar gebruikers-e-mailadres."""

from datetime import timedelta

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.kernel.clock import belgian_today
from tests.conftest import SEEDED_ADMIN_EMAIL


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _activity(db, name, start):
    a = Activity(name=name)
    db.add(a)
    db.flush()
    db.add(ActivityDate(activity_id=a.id, start_date=start))
    db.flush()
    return a


def test_year_headers_on_activiteiten(client, db_session):
    y1 = belgian_today().replace(month=1, day=10) + timedelta(days=400)
    y2 = belgian_today().replace(month=1, day=10) + timedelta(days=800)
    _activity(db_session, "Volgend jaar", y1)
    _activity(db_session, "Jaar erna", y2)
    db_session.commit()

    html = client.get("/activiteiten").text
    assert f">{y1.year}<" in html
    assert f">{y2.year}<" in html


def test_gebruiker_email_is_editable(client, db_session):
    from app.domains.auth.api import User

    csrf = _login(client)
    client.post(
        "/admin/gebruikers",
        data={"email": "oud@example.com", "role_codes": ["ADMIN"]},
        headers={"X-CSRF-Token": csrf},
    )
    user = db_session.query(User).filter(User.email == "oud@example.com").one()

    # De bewerkmodus van het record (#2114) bevat een e-mailinput.
    assert 'name="email"' in client.get(f"/admin/gebruikers/{user.id}?bewerken=1").text

    # E-mail wijzigen via de update-route.
    resp = client.post(
        f"/admin/gebruikers/{user.id}",
        data={"email": "nieuw2@example.com", "is_active": "1"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    db_session.expire_all()
    assert db_session.get(User, user.id).email == "nieuw2@example.com"
