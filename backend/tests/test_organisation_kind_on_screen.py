"""What the organisation kind decides on the screens (CR-12 phase 2 remainder).

Phase 2 made `Organization.org_type` an `OrganizationType` member. Four screens
kept comparing it with a string, and a member equals none:

| Screen | What it decides | Broken as |
|---|---|---|
| organisation list | the badge word and its colour | "organizationtype.account", never blue |
| organisation list | the filter on kind | every filter shows nothing |
| organisation editor | the link to the site settings | gone for every unit |
| tenant list | the platform badge, the code without a slash | the platform as `/platform` |

These tests describe the behaviour of master (v2.6.0, before phase 2). They
were run there first — green — and all four were red on this branch before
the fix; that is how they were found.

A fifth candidate, the newsletter link that `app/ui/__init__.py` hides on the
platform with the same kind of comparison, got no test: the platform's `/` is
the landing page, not `home.html`, so that condition is never read there. A
test for it stayed green with the condition replaced by `True` — it proved
nothing, and was dropped. Written in the spirit of the form
characterisation (`test_form_field_types_characterisation.py`): what worked
before must keep working.

Ids come from the database by kind, not by number (migration 086 could hand
them out in another order; `tenant_lookup.py` says the same).
"""
import re

import pytest
from sqlalchemy import text

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.auth.models import User, UserRole
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _id_of(db, kind: str) -> int:
    return db.execute(text(
        "SELECT id FROM mdm.organizations WHERE org_type = :k AND deleted_at IS NULL "
        "ORDER BY id LIMIT 1"), {"k": kind}).scalar_one()


def _login(client, db, *, operator: bool = False):
    if operator:
        user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
        if not db.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
            db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
            db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _card(html: str, organisation_id: int) -> str:
    start = html.index(f'href="/admin/organisaties/{organisation_id}"')
    return html[start:html.index("</div>\n  </div>", start)]


def test_the_list_badge_names_the_kind_and_colours_the_account(client, db_session):
    _login(client, db_session)
    html = client.get("/admin/organisaties").text

    account = _card(html, _id_of(db_session, "ACCOUNT"))
    unit = _card(html, _id_of(db_session, "UNIT"))
    assert re.search(r"bg-blue-100[^>]*>rechtspersoon<", account), account
    assert re.search(r">afdeling<", unit) and "bg-blue-100" not in unit, unit


def test_the_kind_filter_keeps_only_that_kind(client, db_session):
    _login(client, db_session)
    html = client.get("/admin/organisaties?org_type=UNIT").text

    assert f'href="/admin/organisaties/{_id_of(db_session, "UNIT")}"' in html
    assert f'href="/admin/organisaties/{_id_of(db_session, "ACCOUNT")}"' not in html


def test_the_editor_of_a_unit_links_to_its_site_settings(client, db_session):
    _login(client, db_session)
    unit = _id_of(db_session, "UNIT")
    account = _id_of(db_session, "ACCOUNT")

    assert f'href="/admin/tenants/{unit}"' in client.get(f"/admin/organisaties/{unit}").text
    assert "/admin/tenants/" not in client.get(f"/admin/organisaties/{account}").text, (
        "an ACCOUNT runs no site; a link there ends on a 404")


def test_the_tenant_list_marks_the_platform(client, db_session):
    _login(client, db_session, operator=True)
    html = client.get("/admin/tenants").text
    code = db_session.execute(text(
        "SELECT code FROM mdm.organizations WHERE org_type = 'PLATFORM'")).scalar_one()

    assert f">{code}</span>" in html and f">/{code}</span>" not in html, (
        "the platform opens no site, so its code carries no slash")
    assert ">platform</span>" in html

