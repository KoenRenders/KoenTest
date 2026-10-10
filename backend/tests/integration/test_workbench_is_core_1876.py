"""The workbench is core: no tenant is without it (#1876; Koen, 9 October 2026,
to the choice between making it core and keeping its switch: "1a").

Since CR-24 the workbench is the one way into the back office — where
`back_office_home` sends everyone with a back-office role, where the public
header's Admin item leads, and where the "geen toegang" page points. It was
also a module an operator could switch off, and for such a tenant all three
answered "niet gevonden". Here a tenant with **no module at all** is walked by
a user who holds Boekhouding alone: each of the three ways names the workbench
and the workbench opens.

Red on the master before this change (the module guard on the workbench's
router): each of the three tests fails on 404 where 200 is asked.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    back_office_home,
    make_session_value,
)
from app.domains.mdm import tenant_lookup
from app.domains.mdm.api import invalidate_tenant_codes
from app.kernel.modules import ModuleCode, shown
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

WORKBENCH = "/admin/werkbank"
EMAIL = "boekhouding-1876@example.org"


@pytest.fixture
def treasurer(client, db_session, monkeypatch):
    """Signed in with Boekhouding alone, in a tenant whose module set is empty."""
    create_test_family(db_session, email=EMAIL)
    user = User(email=EMAIL, is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="FINANCE"))
    db_session.commit()
    invalidate_tenant_codes()
    monkeypatch.setattr(tenant_lookup, "_modules_cache", {TENANT_MILLEGEM_ID: frozenset()})
    client.cookies.set(SESSION_COOKIE, make_session_value(EMAIL))
    yield client
    invalidate_tenant_codes()


def test_the_way_in_opens(treasurer, db_session):
    home = back_office_home(db_session, EMAIL)
    assert home == WORKBENCH
    assert treasurer.get(home).status_code == 200


def test_the_public_header_leads_to_a_page_that_opens(treasurer):
    html = treasurer.get("/mijn").text
    links = set(re.findall(r'<a href="([^"]+)"[^>]*data-account-item="admin"', html))
    assert links == {WORKBENCH}, links
    assert treasurer.get(links.pop()).status_code == 200


def test_the_no_access_page_points_to_a_page_that_opens(treasurer):
    refused = treasurer.get("/admin/gebruikers", headers={"accept": "text/html"})
    assert refused.status_code == 403
    way_out = re.search(r'<a[^>]*href="([^"]+)"[^>]*>\s*Naar de werkbank', refused.text)
    assert way_out, "the page names no way to the workbench"
    assert way_out.group(1) == WORKBENCH
    assert treasurer.get(way_out.group(1)).status_code == 200
    menu = re.search(r'<nav id="admin-nav-zijbalk".*?</nav>', refused.text, re.S)
    assert menu and f'href="{WORKBENCH}"' in menu.group(0), "the menu has no workbench"


def test_what_the_module_carried_belongs_to_no_module():
    """Its dashboard tile and its reporting folder are shown whatever is on, and
    no stored set can name it: the code is gone."""
    assert shown("dashboard_tiles", "dashboard_open_tasks", frozenset())
    assert shown("reporting_folders", "Taken", frozenset())
    assert not shown("reporting_folders", "Leden", frozenset()), "the rule reads nothing"
    assert "workflow" not in {code.value for code in ModuleCode}
