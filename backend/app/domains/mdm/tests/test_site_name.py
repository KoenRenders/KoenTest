"""#1546 (CR-19) — a tenant's own "Naam van de site", above Tagline.

Empty, the site shows the name of the organisation behind it (#1550): its own
row by default, its account when the operator pointed it there. Filled in, the
site's own name wins in the header wordmark, the tab title, the footer's "©",
the list of sites (#1543) and the mail sender's name — all of which read
`tenant_display_name`. The field shows the fallback name as its placeholder.

Red against master: there was no field and no column; the site always showed its
own organisation row's name.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.mdm.api import Organization, TenantKind, create_account
from app.kernel.tenancy import TENANT_VOORBEELD_ID

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db, email: str, role: str, tenant_id: int | None) -> str:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code=role, tenant_id=tenant_id))
    db.commit()
    session = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, session)
    return csrf_token_for(session)


def _shown(client, code: str) -> dict[str, str]:
    html = client.get(f"/{code}/").text
    client.cookies.delete("raak_tenant")  # the prefix sets it (#889)
    header = html[html.index("<header") : html.index("</header>")]
    return {
        # The tab title after the environment's "[DEV] " prefix.
        "title": re.search(r"<title>(?:\[\w+\] )?(.*?)</title>", html, re.S).group(1),
        "wordmark": (re.search(r'aria-label="([^"]+)"', header) or [None, ""])[1],
        "footer": re.search(r"© \d{4} ([^<·]+)", html).group(1).strip(),
    }


def _company_under_an_account(db):
    """The seeded Voorbeeldafdeling as a company under a made-up account, its site
    pointed at the account (#1550). A tenant created in a test would not resolve:
    the middleware's code cache reads through a session of its own."""
    account = create_account(db, name="Account Tien", code="tien-1546")
    db.commit()
    site = db.get(Organization, TENANT_VOORBEELD_ID)
    site.parent_id = account.id
    site.kind = TenantKind.COMPANY
    setattr(site, "site_organization_id", account.id)
    db.commit()
    return account, site


def test_empty_the_site_follows_its_organisations_name(client, db_session):
    account, site = _company_under_an_account(db_session)
    shown = _shown(client, site.code)
    print("MEASURE empty", shown)
    assert shown["wordmark"] == "Account Tien" and shown["footer"] == "Account Tien"
    assert shown["title"].startswith("Account Tien")

    account.name = "Account Tien Hernoemd"
    db_session.commit()
    assert _shown(client, site.code)["footer"] == "Account Tien Hernoemd", "it follows"


def test_filled_in_the_sites_own_name_wins_and_stays(client, db_session):
    account, site = _company_under_an_account(db_session)
    csrf = _login(client, db_session, "admin-1546@example.com", "ADMIN", site.id)
    page = client.get(f"/{site.code}/admin/instellingen").text
    client.cookies.delete("raak_tenant")
    field = re.search(r'<input name="site_name"[^>]*>', page).group(0)
    assert 'placeholder="Account Tien"' in field, "the fallback, softly"
    assert page.index('name="site_name"') < page.index('name="tagline"'), "above Tagline"

    saved = client.post(
        f"/{site.code}/admin/instellingen",
        data={"site_name": "Merkzaak Tien", "tagline": ""},
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    client.cookies.delete("raak_tenant")
    assert saved.status_code == 200, saved.text[-300:]
    shown = _shown(client, site.code)
    print("MEASURE filled", shown)
    assert shown == {
        "title": shown["title"],
        "wordmark": "Merkzaak Tien",
        "footer": "Merkzaak Tien",
    }
    assert shown["title"].startswith("Merkzaak Tien")

    account.name = "Account Tien Hernoemd"
    db_session.commit()
    assert _shown(client, site.code)["footer"] == "Merkzaak Tien", "its own name stays"
    from app.kernel.tenant_config import tenant_display_name

    assert tenant_display_name(db_session, site.id) == "Merkzaak Tien", "the mails and the list"
