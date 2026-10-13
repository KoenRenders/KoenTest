"""What the organisation kind decides on the screens (CR-12 phase 2 remainder).

Phase 2 made `Organization.org_type` an `OrganizationType` member. Four screens
kept comparing it with a string, and a member equals none:

| Screen | What it decides | Broken as |
|---|---|---|
| organisation list | the badge word and its colour | "organizationtype.account", never blue |
| organisation list | the filter on kind | every filter shows nothing |
| organisation editor | the link to the site settings | gone for every unit |
| tenant list | the platform's kind badge (#1533), the code without a slash | the platform as `/platform` |

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

import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.auth.models import User, UserRole
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _id_of(db, kind: str) -> int:
    return db.execute(
        text(
            "SELECT id FROM mdm.organizations WHERE org_type = :k AND deleted_at IS NULL "
            "ORDER BY id LIMIT 1"
        ),
        {"k": kind},
    ).scalar_one()


def _login(client, db, *, operator: bool = False):
    if operator:
        user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
        if not db.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
            db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
            db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _row(html: str, organisation_id: int) -> str:
    """The `<tr>` of this organisation's row on the kit's table (#1932)."""
    at = html.index(f'data-organisation="{organisation_id}"')
    return html[html.rindex("<tr", 0, at) : html.index("</tr>", at)]


def test_the_list_badge_names_the_kind_and_colours_the_account(
    client, platform_workspace, db_session
):
    _login(client, db_session)
    html = client.get("/admin/organisaties").text

    account = _row(html, _id_of(db_session, "ACCOUNT"))
    unit = _row(html, _id_of(db_session, "UNIT"))
    # The word is the code list's own, in the Soort cell (#1932): "Account" since #1945.
    assert re.search(r"bg-blue-100[^>]*>Account<", account), account
    assert "rechtspersoon" not in account.lower(), "the old word for the kind (#1945)"
    assert re.search(r">Afdeling<", unit) and "bg-blue-100" not in unit, unit


def test_the_kind_filter_keeps_only_that_kind(client, platform_workspace, db_session):
    _login(client, db_session)
    html = client.get("/admin/organisaties?org_type=UNIT").text

    assert f'data-organisation="{_id_of(db_session, "UNIT")}"' in html
    assert f'data-organisation="{_id_of(db_session, "ACCOUNT")}"' not in html


def test_the_editor_of_a_unit_links_to_its_site_settings(client, platform_workspace, db_session):
    _login(client, db_session)
    unit = _id_of(db_session, "UNIT")
    account = _id_of(db_session, "ACCOUNT")

    assert f'href="/admin/tenants/{unit}"' in client.get(f"/admin/organisaties/{unit}").text
    assert "/admin/tenants/" not in client.get(f"/admin/organisaties/{account}").text, (
        "an ACCOUNT runs no site; a link there ends on a 404"
    )


def test_the_tenant_list_marks_the_platform(client, platform_workspace, db_session):
    _login(client, db_session, operator=True)
    html = client.get("/admin/tenants").text
    code = db_session.execute(
        text("SELECT code FROM mdm.organizations WHERE org_type = 'PLATFORM'")
    ).scalar_one()

    # #1933: the code stands under the name in the row (`ui.row_link`'s sub).
    assert f">{code}</small>" in html and f">/{code}</small>" not in html, (
        "the platform opens no site, so its code carries no slash"
    )
    # #1533: one badge, the kind's; the old blue "platform" badge is gone.
    # `>platform</span>` once: the code itself (its code is "platform"), no second badge.
    assert html.count(">Platform</td>") == 1 and html.count(">platform</small>") == 1


# ── #1945: the kind ACCOUNT is called "Account" ──────────────────────────────

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "203_2026_10_13_093503_the_organisation_kind_account_is_called_.py"
)


def _label(db, language: str) -> str:
    return db.execute(
        text(
            "SELECT value FROM mdm.organization_type_labels "
            "WHERE code = 'ACCOUNT' AND language = :language"
        ),
        {"language": language},
    ).scalar_one()


def _set_label(db, language: str, value: str) -> None:
    db.execute(
        text(
            "UPDATE mdm.organization_type_labels SET value = :value "
            "WHERE code = 'ACCOUNT' AND language = :language"
        ),
        {"language": language, "value": value},
    )


def test_the_kind_account_is_called_account_where_it_is_stored_and_chosen(
    client, platform_workspace, db_session
):
    """#1945 (Koen, 13 October 2026): the kind is a role in the platform, and its
    word is "Account", in both languages. The screens read the code list, so the
    filter of the list offers that word and "Rechtspersoon" nowhere as a kind.

    Broken on purpose (13 October 2026, each put back). The seed's word put
    back to "Rechtspersoon" alone leaves this green: the test database is built
    by the migrations, and the last one rewords the label whatever the seed
    says. With the migration's `upgrade` emptied as well → "assert
    'Rechtspersoon' == 'Account'", and the list's badge test red with it. The
    migration is what carries the word on an environment; the seed keeps a
    database built from scratch from saying the old word in between."""
    assert _label(db_session, "nl") == "Account"
    assert _label(db_session, "en") == "Account"

    _login(client, db_session)
    html = client.get("/admin/organisaties").text
    # The kinds are the toolbar's segments since #1932: a radio and its word.
    options = re.findall(
        r'<input type="radio" name="org_type" value="(ACCOUNT|UNIT|PLATFORM)"[^>]*>\s*'
        r"<span[^>]*>([^<(]+?)\s*(?:<span|</span)",
        html,
    )
    assert dict(options) == {"ACCOUNT": "Account", "UNIT": "Afdeling", "PLATFORM": "Platform"}, (
        options
    )
    assert ">rechtspersoon<" not in html.lower(), "the old word shows as a kind"


def test_the_migration_rewords_the_old_word_and_nothing_else(db_session):
    """An environment carries the word migration 154 seeded; this migration
    replaces it — twice without harm, and not a word somebody else put there.
    The downgrade gives the old word back. Broken on purpose: the guard on the
    old word (`AND value = :old`) out of the migration → "a word of somebody
    else was overwritten"."""
    spec = importlib.util.spec_from_file_location("migration_account_word", MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    bind = db_session.connection()
    _set_label(db_session, "nl", "Rechtspersoon")
    _set_label(db_session, "en", "Customer")

    migration.reword(bind, 0, 1)
    migration.reword(bind, 0, 1)

    assert _label(db_session, "nl") == "Account"
    assert _label(db_session, "en") == "Customer", "a word of somebody else was overwritten"

    migration.reword(bind, 1, 0)
    assert _label(db_session, "nl") == "Rechtspersoon", "the downgrade does not restore the word"
    db_session.rollback()
