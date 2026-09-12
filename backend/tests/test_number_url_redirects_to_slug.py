"""#890 — the number URL redirects to the friendly one, so sharing works by itself.

#884 delivered one route that accepts both keys. Open the album with the number and you stay
on the number; only a `canonical` tag in the source says the slug is the real address.

**People share from the address bar.** They copy what is there, or press the share button on
their phone. Nobody reads a canonical tag — so the number keeps circulating and the friendly
URL is built but unused.

A copy button was considered and rejected: a second place that also has to be right, and it
competes with what everybody already does.

**Temporary and not permanent (307).** A permanent redirect is remembered by the browser and
is very hard to undo; if a slug ever turns out wrong, or disappears, people keep landing on a
dead address out of their own cache. Search engines already know which one is real from the
canonical tag, so this costs nothing.

Broken on purpose to check that these tests can go red: the 307 changed to a 301 → the status
test falls over, and that is the detail that quietly changes in a rewrite; the `activity_key
!= slug` guard dropped → the slug URL redirects to itself and the test hits a redirect loop.
"""
from datetime import date

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _activity(db, *, name="Zomerfeest", slug=None):
    activity = Activity(name=name, slug=slug)
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2026, 7, 1)))
    db.flush()
    return activity


def test_the_number_url_redirects_to_the_slug(client, db_session):
    activity = _activity(db_session, slug="zomerfeest-2026")

    resp = client.get(f"/activiteiten/{activity.id}/fotos", follow_redirects=False)

    assert resp.status_code == 307, (
        f"{resp.status_code} — een permanente doorverwijzing wordt door de browser "
        f"onthouden en krijg je nauwelijks nog weg")
    assert resp.headers["location"] == "/activiteiten/zomerfeest-2026/fotos"

    gevolgd = client.get(f"/activiteiten/{activity.id}/fotos")
    assert gevolgd.status_code == 200
    assert "Zomerfeest" in gevolgd.text


def test_without_a_slug_nothing_redirects(client, db_session):
    """De test die verhindert dat de doorverwijzing een lus of een 404 wordt op de
    gevallen die vandaag normaal zijn — verreweg de meeste activiteiten."""
    activity = _activity(db_session, name="Zonder adres", slug=None)

    resp = client.get(f"/activiteiten/{activity.id}/fotos", follow_redirects=False)

    assert resp.status_code == 200, resp.text[:200]
    assert "Zonder adres" in resp.text


def test_the_slug_url_does_not_redirect_to_itself(client, db_session):
    """Zonder de vergelijking met de gevraagde sleutel stuurt de slug-URL naar zichzelf
    en loopt het rond."""
    _activity(db_session, name="Kerstmarkt", slug="kerstmarkt-2026")

    resp = client.get("/activiteiten/kerstmarkt-2026/fotos", follow_redirects=False)

    assert resp.status_code == 200, (
        f"{resp.status_code} — de slug-URL verwijst door, dus dit draait rond")


def test_an_admin_path_with_a_number_does_not_redirect(client, db_session):
    """De beheerschermen werken met het nummer en blijven ongemoeid."""
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db_session.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    activity = _activity(db_session, name="Beheerd", slug="beheerd-2026")

    resp = client.get(f"/admin/activiteiten/{activity.id}", follow_redirects=False)

    assert resp.status_code == 200, f"{resp.status_code} — het beheerscherm verwijst door"


def test_after_the_redirect_the_canonical_matches_the_address_bar(client, db_session):
    """Twee verschillende antwoorden op "welk adres is dit" is waar dit issue over gaat."""
    activity = _activity(db_session, name="Buurtfeest", slug="buurtfeest-2026")

    resp = client.get(f"/activiteiten/{activity.id}/fotos")

    assert str(resp.url).endswith("/activiteiten/buurtfeest-2026/fotos"), resp.url
    canonical = resp.text.split('rel="canonical" href="', 1)[1].split('"', 1)[0]
    assert canonical.endswith("/activiteiten/buurtfeest-2026/fotos"), canonical
