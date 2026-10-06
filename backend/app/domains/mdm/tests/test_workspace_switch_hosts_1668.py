"""#1668 — the switcher links a workspace on the host where it can be reached.

Found on UAT after v2.13.0: on a department's own domain, choosing the
platform opened the department again. The switcher linked the platform
relative to the request's host, and on a department's host every path is the
department. #1536 fixed "on a platform host the cookie wins"; this is the other
case, "not on a platform host at all" — invisible where one host serves
everything.

Each workspace has its host: a department with a host of its own there, the
platform and a department without one on a platform host (the one source:
`platform_home_url`, the first of `PLATFORM_HOSTS`).

Broken on purpose (6 October 2026), each red for its own reason:

- the platform's link built from the request's host again → the first test;
- a department without a host linked relative on another department's host →
  the same test, its second assertion;
- the route answering `/admin` on a department's host → the route test;
- on a platform host the first host of the list taken instead of this one →
  the second-platform-host test (#860);
- the rule applied without `PLATFORM_HOSTS` → the one-host test: the links
  follow `FRONTEND_URL` to a host nobody is on.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.mdm.api import invalidate_tenant_codes, platform_tenant_id
from app.kernel.tenancy import TENANT_MILLEGEM_ID

pytestmark = pytest.mark.ui_serverrendered

PLATFORM = "platform.example"
SECOND_PLATFORM = "beheer.example"
OWN = "afdeling.example"  # the own domain of raakmillegem in these tests
OTHER = "raakvoorbeeldafdeling"  # a department without a domain


@pytest.fixture
def hosts(monkeypatch):
    """An environment with two platform hosts and one department on its own
    domain, served over https on the default port."""
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_url", f"https://{OWN}")
    monkeypatch.setattr(settings, "platform_hosts", f"{PLATFORM},{SECOND_PLATFORM}")
    monkeypatch.setattr(settings, "tenant_hostnames", f"{OWN}=raakmillegem")
    invalidate_tenant_codes()
    yield
    invalidate_tenant_codes()


@pytest.fixture
def operator(client, db_session):
    user = User(email="operator-1668@example.com", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="OPERATOR", tenant_id=None))
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(user.email))
    return platform_tenant_id(db_session)


def _links(client, host: str) -> set[str]:
    page = client.get("/admin/werkruimte-wisselen", headers={"host": host})
    assert page.status_code == 200, page.status_code
    return set(re.findall(r'href="([^"]*(?:/admin|werkruimte-wisselen/\d+))"', page.text))


def test_on_a_departments_own_host_the_platform_and_the_others_are_linked_on_a_platform_host(
    client, hosts, operator
):
    """Red on master: the platform's link carried the department's host, and
    the other department was `/<code>/admin` on this host."""
    links = _links(client, OWN)

    assert f"https://{PLATFORM}/admin/werkruimte-wisselen/{operator}" in links
    assert f"https://{PLATFORM}/{OTHER}/admin" in links
    # the department whose host this is stays here, without a prefix
    assert "/admin" in links
    assert not [href for href in links if OWN in href], links
    assert f"/{OTHER}/admin" not in links and "/raakmillegem/admin" not in links


def test_on_a_platform_host_nothing_leaves_it_but_a_department_with_its_own_host(
    client, hosts, operator
):
    links = _links(client, PLATFORM)

    assert f"/admin/werkruimte-wisselen/{operator}" in links, "the platform stays on this host"
    assert f"/{OTHER}/admin" in links, "a department without a host keeps its prefix here"
    assert f"https://{OWN}/admin" in links, "a department with a host opens on that host"
    assert not [href for href in links if PLATFORM in href], links


def test_on_the_second_platform_host_the_platform_stays_on_that_host(client, hosts, operator):
    """#860: never a link to another host of the list than the one you are on."""
    links = _links(client, SECOND_PLATFORM)

    assert f"/admin/werkruimte-wisselen/{operator}" in links
    assert f"/{OTHER}/admin" in links
    assert not [href for href in links if PLATFORM in href], links


def test_the_route_on_a_departments_host_sends_the_choice_to_the_host_that_serves_it(
    client, hosts, operator
):
    """An old link, a bookmark: the route itself must not answer `/admin` on a
    host where that is the department. Red on master."""
    to_platform = client.get(
        f"/admin/werkruimte-wisselen/{operator}", headers={"host": OWN}, follow_redirects=False
    )
    assert to_platform.status_code == 303
    assert to_platform.headers["location"] == (
        f"https://{PLATFORM}/admin/werkruimte-wisselen/{operator}"
    )
    assert "raak_tenant" not in to_platform.headers.get("set-cookie", ""), (
        "the cookie to clear lives on the platform host, not here"
    )

    other = next(t for t, code in _codes(client).items() if code == OTHER)
    to_other = client.get(
        f"/admin/werkruimte-wisselen/{other}", headers={"host": OWN}, follow_redirects=False
    )
    assert to_other.headers["location"] == f"https://{PLATFORM}/{OTHER}/admin"

    home = client.get(
        f"/admin/werkruimte-wisselen/{TENANT_MILLEGEM_ID}",
        headers={"host": PLATFORM},
        follow_redirects=False,
    )
    assert home.headers["location"] == f"https://{OWN}/admin"


def _codes(client) -> dict[int, str]:
    from app.database import SessionLocal
    from app.domains.mdm.api import list_manageable_tenants

    db = SessionLocal()
    try:
        return {org.id: org.code for org in list_manageable_tenants(db)}
    finally:
        db.close()


def test_on_a_platform_host_the_route_clears_the_cookie_as_before(client, hosts, operator):
    """#1536, unchanged."""
    answer = client.get(
        f"/admin/werkruimte-wisselen/{operator}", headers={"host": PLATFORM}, follow_redirects=False
    )
    assert answer.status_code == 303 and answer.headers["location"] == "/admin"
    cleared = answer.headers.get("set-cookie", "")
    assert cleared.startswith("raak_tenant=") and "Max-Age=0" in cleared, cleared


def test_where_one_host_serves_everything_the_links_stay_relative(client, operator, monkeypatch):
    """No `PLATFORM_HOSTS` (HDEV, a developer's machine): there is no other
    host to go to, whatever `FRONTEND_URL` says."""
    from app.config import settings

    monkeypatch.setattr(settings, "platform_hosts", "")
    monkeypatch.setattr(settings, "tenant_hostnames", "")
    monkeypatch.setattr(settings, "frontend_url", "https://elders.example")
    invalidate_tenant_codes()

    links = _links(client, "testserver")

    assert f"/admin/werkruimte-wisselen/{operator}" in links
    assert "/raakmillegem/admin" in links and f"/{OTHER}/admin" in links
    assert not [href for href in links if href.startswith("http")], links
