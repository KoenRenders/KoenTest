"""#1543 (CR-19) — the platform's home is an ordinary CMS page, and a placeholder
lists accounts with their sites on any site's page.

- The platform's `/` renders its home page (`is_home`, #1477) in the site shell:
  the page migration 193 made from #1525's text, titled with the platform
  organisation's name, the list where the old landing put it; there is no
  home-intro block left, and editing the page in Pagina's changes the home.
- `{{tenants}}` on a department's page lists every active account with its active
  tenants, "Overige" last; `{{tenants:<code>}}` lists one account's sites; an
  inactive tenant is absent; the platform stands under its account once it has
  one (#1542).
- The header has the ordinary "Aanmelden", and the sign-in screen answers on the
  platform host (the mail link itself: `test_absolute_urls_follow_the_host`).

Red against master: the platform's `/` was the fixed landing template, there was
no `{{tenants}}`, and the platform had no page of its own.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.cms.api import CmsPage
from app.domains.mdm.api import (
    Organization,
    OrganizationType,
    create_account,
    create_tenant,
)
from app.kernel.tenancy import TENANT_MILLEGEM_ID

pytestmark = pytest.mark.ui_serverrendered


def _platform(db) -> Organization:
    return (
        db.query(Organization)
        .filter(Organization.org_type == OrganizationType.PLATFORM)
        .execution_options(include_all_tenants=True)
        .one()
    )


def _pages(db, tenant_id: int) -> dict[str, CmsPage]:
    rows = (
        db.query(CmsPage)
        .filter(CmsPage.tenant_id == tenant_id)
        .execution_options(include_all_tenants=True)
        .all()
    )
    return {p.slug: p for p in rows}


def _groups(html: str) -> dict[str | None, list[str]]:
    """The placeholder's output: each `<h3>` with the site names of the cards in
    its grid (#1566); a grid without a heading under None."""
    groups: dict[str | None, list[str]] = {}
    for block in re.findall(
        r"<div hx-boost=\"false\" data-tenant-sites>.*?</div>\s*</div>", html, re.S
    ):
        for m in re.finditer(
            r"(?:<h3>(.*?)</h3>\s*)?<div class=\"grid[^>]*>(.*?)</div>", block, re.S
        ):
            groups[m.group(1)] = re.findall(
                r"<a [^>]*data-site-card[^>]*><span[^>]*>(.*?)</span>", m.group(2)
            )
    return groups


def _department_page(db, content: str) -> None:
    db.add(
        CmsPage(
            tenant_id=TENANT_MILLEGEM_ID,
            slug="onze-netwerk-1543",
            title="Ons netwerk",
            content=content,
            is_published=True,
            show_in_nav=False,
        )
    )
    db.commit()


def test_the_platform_home_is_its_cms_page_without_a_home_intro(platform_workspace, db_session):
    client = platform_workspace
    platform = _platform(db_session)
    pages = _pages(db_session, platform.id)
    assert "home-intro" not in pages, "the block's text moved into the page"
    home = pages["start"]
    assert home.is_home and home.is_published and not home.show_in_nav
    assert home.title == platform.name, "the title follows the organisation's name"
    assert "{{tenants}}" in home.content

    html = client.get("/").text
    assert 'data-shell="site"' in html, "the ordinary site shell"
    assert "Eén platform voor verenigingen en organisaties" in html
    assert "Raak Millegem" in _groups(html).get("Raak", []), "the list where the landing had it"
    assert 'href="/aanmelden"' in html and "Aanmelden" in html
    assert client.get("/aanmelden").status_code == 200, "sign-in answers on the platform host"


def test_editing_the_platform_home_in_paginas_changes_it(platform_workspace, db_session):
    client = platform_workspace
    user = User(email="operator-1543@example.com", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="OPERATOR"))
    db_session.commit()
    session = make_session_value("operator-1543@example.com")
    client.cookies.set(SESSION_COOKIE, session)
    home = _pages(db_session, _platform(db_session).id)["start"]

    saved = client.post(
        f"/admin/paginas/{home.id}",
        data={
            "title": home.title,
            "slug": "start",
            "content": "<p>Welkom op ons platform, in eigen woorden.</p><p>{{tenants}}</p>",
            "is_published": "1",
            "is_home": "1",
        },
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    assert saved.status_code == 200, saved.text[-400:]
    client.cookies.clear()
    html = client.get("/").text
    assert "Welkom op ons platform, in eigen woorden." in html
    assert "Eén platform voor verenigingen" not in html


def test_the_placeholder_on_a_department_page(client, db_session):
    first = create_account(db_session, name="Account Vijf", code="vijf-1543")
    second = create_account(db_session, name="Account Zes", code="zes-1543")
    create_tenant(db_session, name="Clubhuis", code="clubhuis-1543", parent_id=first.id)
    closed = create_tenant(
        db_session, name="Gesloten Club", code="gesloten-1543", parent_id=first.id
    )
    closed.is_active = False
    create_tenant(db_session, name="Werkplaats", code="werkplaats-1543", parent_id=second.id)
    platform = _platform(db_session)
    platform.parent_id = second.id
    db_session.commit()
    _department_page(db_session, "<p>{{tenants}}</p><p>---</p><p>{{tenants:vijf-1543}}</p>")

    html = client.get("/onze-netwerk-1543").text
    everything, one = html.split("---", 1)
    groups = _groups(everything)
    print("MEASURE", groups, _groups(one))
    assert groups["Account Vijf"] == ["Clubhuis"], "an inactive tenant is absent"
    assert sorted(groups["Account Zes"]) == sorted(["Werkplaats", platform.name]), (
        "the platform under its account (#1542)"
    )
    assert "Raak Millegem" in groups["Raak"]
    assert _groups(one) == {None: ["Clubhuis"]}, "one account, without a heading"
    assert everything.count('<div hx-boost="false" data-tenant-sites>') == 1, (
        "a link to another site is not boosted"
    )


def test_each_site_is_a_card_that_is_a_link_as_a_whole(client, db_session):
    """#1566: one card link per site — its name, and its address under it — in a
    grid per account, and no list. Both forms of the placeholder. Red against
    master, where the placeholder rendered `<ul><li><a>`."""
    account = create_account(db_session, name="Account Acht", code="acht-1566")
    create_tenant(db_session, name="Atelier <Noord>", code="atelier-1566", parent_id=account.id)
    create_tenant(db_session, name="Buurthuis", code="buurthuis-1566", parent_id=account.id)
    db_session.commit()
    _department_page(db_session, "<p>{{tenants}}</p><p>---</p><p>{{tenants:acht-1566}}</p>")

    html = client.get("/onze-netwerk-1543").text
    for part in html.split("---", 1):
        block = re.search(r"data-tenant-sites>(.*?)</div>\s*</div>", part, re.S).group(1)
        assert "<ul" not in block and "<li" not in block
        cards = re.findall(
            r'<a href="([^"]+)" data-site-card[^>]*><span[^>]*>(.*?)</span><span[^>]*>(.*?)</span></a>',
            block,
        )
        names = [name for _url, name, _address in cards]
        assert block.count("<a ") == len(cards), "every link in the block is a card"
        assert "Buurthuis" in names and "Atelier &lt;Noord&gt;" in names, "names are escaped"
        assert all(url == address and url for url, _name, address in cards), (
            "the address under the name"
        )
        assert "grid-cols-1 sm:grid-cols-2" in block
    assert len(re.findall(r"data-site-card", html.split("---", 1)[1])) == 2, (
        "one account: its two sites"
    )


def test_the_placeholder_leaves_the_platform_out_without_an_account(client, db_session):
    _department_page(db_session, "<p>{{tenants}}</p><p>{{tenants:bestaat-niet}}</p>")
    html = client.get("/onze-netwerk-1543").text
    names = [name for group in _groups(html).values() for name in group]
    assert _platform(db_session).name not in names
    assert "{{tenants" not in html, "an unknown account code renders nothing, not the code"
