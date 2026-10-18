"""A tenant code that equals the first segment of a route is refused (#1951).

The path prefix wins over the route (`tenancy.resolve_request`): a tenant with
the code `admin` would take the back office away from every tenant, `api` the
payment provider's webhook. Nothing refused such a code; `_check_code` held the
form and uniqueness only.

The reserved words are read from the route table when the check runs
(`kernel.route_table`), so a route added later is reserved by existing — the
test adds one and finds it refused.

Broken on purpose (15 October 2026, put back): the check taken out of
`_check_code` → six tests fail: the four tenant codes, the
route added in the test, and the screen, which no longer shows the sentence.
"""

from __future__ import annotations

import logging

import pytest

from app.domains.mdm.api import TenantFout
from tests._sites import new_site

pytestmark = pytest.mark.ui_agnostisch


@pytest.mark.parametrize("code", ["admin", "api", "activiteiten", "static"])
def test_a_code_that_is_a_route_is_refused(db_session, code):
    with pytest.raises(TenantFout, match=f"/{code}/"):
        new_site(db_session, name="Botsing", code=code)


def test_an_ordinary_code_is_accepted(db_session):
    org = new_site(db_session, name="Raak Proef", code="raakproef-1951")
    assert org.code == "raakproef-1951"


def test_a_route_added_later_is_reserved_by_existing(db_session):
    """Derived, not listed: a route this test adds is reserved at once, and
    no longer once it is gone."""
    from app.kernel.route_table import reserved_segments
    from app.main import app

    assert "proefroute-1951" not in reserved_segments()
    app.add_api_route("/proefroute-1951/iets", lambda: {})
    try:
        assert "proefroute-1951" in reserved_segments()
        with pytest.raises(TenantFout, match="/proefroute-1951/"):
            new_site(db_session, name="Botsing", code="proefroute-1951")
    finally:
        app.router.routes.pop()
    assert "proefroute-1951" not in reserved_segments()


def test_a_path_parameter_reserves_nothing():
    """The CMS's `/{slug}` catch-all is a route too; its parameter is no word."""
    from app.kernel.route_table import reserved_segments

    assert not any(word.startswith("{") for word in reserved_segments())
    assert {"admin", "api", "static"} <= reserved_segments()


def test_why_the_refusal_exists_the_prefix_wins_over_the_route():
    """Today's resolution, kept as the reason: with `admin` among the codes, the
    back office's own path resolves to that tenant and loses its first segment."""
    from app.kernel.tenancy import resolve_request

    tenant, rest = resolve_request(
        "localhost", "/admin/leden", None, {}, set(), codes={"admin": 99}
    )
    assert (tenant, rest) == (99, "/leden")


def test_startup_logs_a_code_that_meets_a_route(db_session, monkeypatch, caplog):
    """The other direction: a route added after a tenant got that code. Reported
    as an ERROR at startup, never a refused start."""
    import app.domains.mdm.api as mdm_api
    from app.main import _report_tenant_code_collisions

    monkeypatch.setattr(mdm_api, "tenant_codes", lambda db=None: {"admin": 99, "raakproef": 98})
    with caplog.at_level(logging.ERROR, logger="app.main"):
        _report_tenant_code_collisions()
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1 and "'admin'" in errors[0]


def test_the_operator_reads_the_refusal_on_the_tenants_screen(
    client, platform_workspace, db_session
):
    from app.domains.auth.api import (
        SESSION_COOKIE,
        User,
        UserRole,
        csrf_token_for,
        make_session_value,
    )
    from app.domains.mdm.models import Organization

    user = User(email="operator-1951@example.com", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
    db_session.flush()
    session = make_session_value(user.email)
    client.cookies.set(SESSION_COOKIE, session)

    page = client.post(
        "/admin/tenants",
        data={"name": "Botsing", "code": "admin", "kind": "VERENIGING"},
        headers={"X-CSRF-Token": csrf_token_for(session)},
    )
    assert "De code admin is een adres van de toepassing zelf" in page.text
    assert db_session.query(Organization).filter(Organization.name == "Botsing").count() == 0
