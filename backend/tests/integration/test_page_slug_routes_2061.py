"""A page's address that the application or a tenant already answers on is refused (#2061).

The public page route is `/{slug}`, the last word of the route table: a fixed route
with the same first segment answers first (`/activiteiten` is the activities), and a
tenant's code is taken as the path prefix before any route is asked
(`tenancy.resolve_request`: `/raak` is that tenant's home). A page with such an
address was saved and never served, without an error. #1951 refused the same
collision for a tenant code; the page slug had no check.

Measured before the change (16 October 2026, a published page stored with the slug
of a tenant code): `GET /<code>` answered that tenant's home page, not the page.

The check reads the route table (`kernel.route_table.colliding`, #1951) and mdm's
live tenant codes (`tenant_codes`) when it runs: no list of its own. One helper in
`cms.service` holds it for making a page and for both doors that rename one.

Broken on purpose (16 October 2026, each put back):
- the two new checks taken out of `_check_slug` → every refusal test of a route
  and of a tenant code fails, the screen tests with them;
- the `.lower()` taken out of `_check_code` → the upper-case test fails: the code
  is then refused for its form ("Naam én een geldige code …"), not as one that
  exists.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.cms.api import CmsPage, SlugBestaatAl, create_page, update_page
from app.schemas.cms import CmsPageCreate, CmsPageUpdate
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

ROUTE = "is een adres van de toepassing zelf"
TENANT = "is het adres van een afdeling"


@pytest.fixture
def headers(client) -> dict[str, str]:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _a_tenant_code(db) -> str:
    from app.domains.mdm.api import tenant_codes

    codes = sorted(tenant_codes(db))
    assert codes, "no tenant code to collide with"
    return codes[0]


def _pages(db) -> int:
    db.expire_all()
    return db.query(CmsPage).count()


@pytest.mark.parametrize("slug", ["activiteiten", "admin", "lid-worden"])
def test_a_new_page_at_a_route_is_refused(db_session, slug):
    before = _pages(db_session)
    with pytest.raises(SlugBestaatAl, match=f"/{slug} {ROUTE}"):
        create_page(db_session, CmsPageCreate(title="Botsing", slug=slug))
    assert _pages(db_session) == before


def test_a_new_page_at_a_tenant_code_is_refused(db_session):
    code = _a_tenant_code(db_session)
    with pytest.raises(SlugBestaatAl, match=f"/{code} {TENANT}"):
        create_page(db_session, CmsPageCreate(title="Botsing", slug=code))


def test_a_page_cannot_be_renamed_to_a_route(db_session):
    page = create_page(db_session, CmsPageCreate(title="Over ons", slug="over-ons-2061"))
    with pytest.raises(SlugBestaatAl, match=ROUTE):
        update_page(db_session, page.id, CmsPageUpdate(slug="activiteiten"))
    db_session.expire_all()
    assert page.slug == "over-ons-2061"


def test_an_ordinary_address_and_an_unchanged_one_are_accepted(db_session):
    page = create_page(db_session, CmsPageCreate(title="Over ons", slug="over-ons-2061"))
    update_page(db_session, page.id, CmsPageUpdate(title="Over ons!", slug="over-ons-2061"))
    db_session.expire_all()
    assert (page.title, page.slug) == ("Over ons!", "over-ons-2061")


def test_a_route_added_later_is_reserved_by_existing(db_session):
    """Derived, not listed: a route the test adds is refused at once."""
    from app.main import app

    app.add_api_route("/proefroute-2061/iets", lambda: {})
    try:
        with pytest.raises(SlugBestaatAl, match=ROUTE):
            create_page(db_session, CmsPageCreate(title="Botsing", slug="proefroute-2061"))
    finally:
        app.router.routes.pop()


def test_the_record_screen_shows_the_refusal_under_the_address(client, db_session, headers):
    page = create_page(db_session, CmsPageCreate(title="Over ons", slug="over-ons-2061"))
    db_session.commit()

    answer = client.post(
        f"/admin/paginas/{page.id}",
        data={"title": "Over ons", "slug": "activiteiten", "document": ""},
        headers={**headers, "HX-Request": "true"},
    )

    assert answer.status_code == 200, answer.text
    assert 'id="cp-slug-error"' in answer.text, "the reason stands under the address field"
    assert f"/activiteiten {ROUTE}" in answer.text
    assert 'aria-invalid="true"' in answer.text
    assert 'value="activiteiten"' in answer.text, "the field keeps the address as typed"
    db_session.expire_all()
    assert db_session.get(CmsPage, page.id).slug == "over-ons-2061"


def test_the_new_page_screen_shows_the_refusal(client, db_session, headers):
    before = _pages(db_session)
    code = _a_tenant_code(db_session)

    route = client.post(
        "/admin/paginas", data={"title": "Botsing", "slug": "activiteiten"}, headers=headers
    )
    tenant = client.post("/admin/paginas", data={"title": "Botsing", "slug": code}, headers=headers)

    assert route.status_code == 422 and f"/activiteiten {ROUTE}" in route.text
    assert route.headers["HX-Retarget"] == "#pagina-nieuw-melding"
    assert tenant.status_code == 422 and f"/{code} {TENANT}" in tenant.text
    assert _pages(db_session) == before, "a refused page was made"


def test_a_tenant_code_in_upper_case_is_the_same_code(db_session):
    """#2061's third point: `Admin` and `admin` cannot both exist. `_check_code`
    lower-cases before it looks for the code, so a second tenant `RaakProef-2061`
    is refused as the code that exists."""
    from app.domains.mdm.api import TenantFout, create_tenant

    create_tenant(db_session, name="Raak Proef", code="raakproef-2061")
    with pytest.raises(TenantFout, match="Die code bestaat al."):
        create_tenant(db_session, name="Raak Proef twee", code="RaakProef-2061")
