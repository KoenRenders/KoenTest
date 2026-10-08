"""A signed-in user without the role gets a calm page, not bare JSON (#1583).

`_require_ui_roles` answers 403 for a signed-in user whose role may not see the
screen. Until #1583 a browser showed `{"detail": "Geen toegang"}`. One handler
(`app.main`, `app.ui.no_access`) now renders a page for a browser navigation to
an admin screen — and for nothing else: the JSON API, an htmx fragment and a
write keep their plain 403, and a visitor without a session is still sent to
the sign-in screen (#1458).

The button goes where signing in would have taken this user
(`auth.landing_for`), and that place answers 200 for them.

Broken on purpose to see these tests red, six times: the handler left out of
`app.main` (every page test gets JSON — this is "red against master"); the
`HX-Request` check dropped (a fragment gets a whole page); the method check
dropped (a refused POST gets the page); the `Accept` check dropped (a JSON
client gets the page); the way out fixed to the workbench (the FINANCE user's
button answers 403); and the admin shell for everyone (a user without any admin
screen gets a menu of nothing).
"""

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    csrf_token_for,
    make_session_value,
)

pytestmark = pytest.mark.ui_serverrendered

BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
SENTENCE = "Je hebt geen toegang tot dit scherm."


def _signed_in(client, db, email: str, *roles: str) -> dict:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role_code=role))
    db.commit()
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _way_out(html: str) -> str:
    import re

    assert html.count("data-no-access-way-out") == 1, "one button"
    return re.search(r'<a href="([^"]+)"[^>]*data-no-access-way-out', html).group(1)


def test_a_finance_user_on_a_general_admin_screen_gets_the_page_and_a_way_to_payments(
    client, db_session
):
    """A screen FINANCE may not see. The page keeps the user's own navigation —
    only what the role may open — and the button's target answers 200."""
    _signed_in(client, db_session, "penning@example.com", "FINANCE")
    for screen in ("/admin/activiteiten", "/admin/leden"):
        answer = client.get(screen, headers=BROWSER)
        assert answer.status_code == 403, "the status stays 403"
        assert answer.headers["content-type"].startswith("text/html")
        html = answer.text
        assert "data-no-access" in html and SENTENCE in html
        assert '{"detail"' not in html
        assert _way_out(html) == "/admin/betalingen"
        assert 'href="/admin/leden"' not in html, "no navigation the role may not open"
    assert client.get("/admin/betalingen", headers=BROWSER).status_code == 200


def test_an_admin_on_an_operator_only_screen_gets_the_page_and_a_way_to_the_workbench(
    client, platform_workspace, db_session
):
    """Tenants is the operator's, in the platform workspace (#1535)."""
    _signed_in(client, db_session, "bestuur@example.com", "ADMIN")
    answer = client.get("/admin/tenants", headers=BROWSER)
    assert answer.status_code == 403
    assert "data-no-access" in answer.text and SENTENCE in answer.text
    target = _way_out(answer.text)
    # #1740: the page a role enters the back office by (`back_office_home`).
    assert target == "/admin"
    assert client.get(target, headers=BROWSER).status_code == 200


def test_a_user_without_any_admin_screen_gets_the_page_in_the_sites_shell(client, db_session):
    """No role at all: the admin shell would be a menu of nothing. The page stands
    in the site's shell and the button leaves the back office."""
    _signed_in(client, db_session, "lid@example.com")
    answer = client.get("/admin/betalingen", headers=BROWSER)
    assert answer.status_code == 403
    assert "data-no-access" in answer.text and SENTENCE in answer.text
    assert 'data-shell="site"' in answer.text
    target = _way_out(answer.text)
    assert not target.startswith("/admin")
    assert client.get(target, headers=BROWSER).status_code == 200


def test_the_page_carries_no_record_data(client, db_session):
    """§3.18: one sentence and the way out — nothing of what was asked for."""
    from tests.conftest import seed_activity_with_product

    activity, _c, _p = seed_activity_with_product(db_session)
    activity.name = "Geheime wandeling"
    db_session.commit()
    _signed_in(client, db_session, "penning@example.com", "FINANCE")
    answer = client.get(f"/admin/activiteiten/{activity.id}", headers=BROWSER)
    assert answer.status_code == 403 and "data-no-access" in answer.text
    assert "Geheime wandeling" not in answer.text


def test_a_fragment_a_write_and_a_json_request_keep_the_plain_403(client, db_session):
    """An htmx request must not get a whole page inside its target; a POST stays
    refused; a client that asks for JSON gets JSON."""
    headers = _signed_in(client, db_session, "penning@example.com", "FINANCE")
    plain = {"detail": "Geen toegang"}
    fragment = client.get("/admin/activiteiten", headers={**BROWSER, "HX-Request": "true"})
    assert fragment.status_code == 403 and fragment.json() == plain
    write = client.post(
        "/admin/activiteiten/nieuw", headers={**BROWSER, **headers}, data={"name": "x"}
    )
    assert write.status_code == 403 and write.json() == plain
    json_client = client.get("/admin/activiteiten", headers={"Accept": "application/json"})
    assert json_client.status_code == 403 and json_client.json() == plain


def test_the_json_api_still_answers_json(client, db_session):
    _signed_in(client, db_session, "penning@example.com", "FINANCE")
    answer = client.get("/api/v1/users", headers=BROWSER)
    assert answer.status_code in (401, 403)
    assert answer.headers["content-type"].startswith("application/json")
    assert "detail" in answer.json() and "data-no-access" not in answer.text


def test_a_visitor_without_a_session_is_still_sent_to_the_sign_in_screen(client):
    answer = client.get("/admin/activiteiten", headers=BROWSER, follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"].startswith("/aanmelden?terug=")


@pytest.mark.parametrize(
    "screen",
    [
        "/admin/ledenwijzigingen",
        "/admin/ledenwijzigingen/export",
        "/admin/e-maillog",
        "/admin/info",
        # The media cut of the same phase: the library and its upload form.
        "/admin/media",
        "/admin/media/nieuw",
        # The chatbot cut: what Raakje knows.
        "/admin/ai-context",
    ],
)
def test_the_screens_whose_json_routes_went_ask_for_a_sign_in(client, screen):
    """The change feed, the e-mail log and the system info are reachable through
    their screens only since their JSON routes went (CR-13 phase 4b, #1251); the
    routes' own "no token → 401" tests went with them, this is the screens'.

    Proven red (8 October 2026): `require_admin_ui` taken off the system info
    screen → its case answers 200.
    """
    answer = client.get(screen, headers=BROWSER, follow_redirects=False)
    assert answer.status_code == 303, screen
    assert answer.headers["location"].startswith("/aanmelden?terug=")
