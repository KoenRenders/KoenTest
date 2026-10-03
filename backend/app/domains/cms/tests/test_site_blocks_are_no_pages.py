"""#1510 — a site block is not a page: not in the sitemap, not at its own address.

The sitemap of a new tenant listed `/home-intro` and `/site-footer`: the two
blocks #1478 seeds are published `CmsPage` rows, and the sitemap took every
published row. Measured before building: no kind marks a block, and
`show_in_nav=False` marks real pages too (`privacy`), so a block is known by its
slug (`SITE_BLOCK_SLUGS`). One test, `is_page`, decides for the sitemap and for
the public page route.

The association's sitemap keeps every real page: everything published that is
not a block, a page out of the menu (`privacy`) included.

Red against master: the sitemap listed both blocks and `/home-intro` answered
200 as a page.
"""

from __future__ import annotations

import re

import pytest

from app.domains.cms.api import SITE_BLOCK_SLUGS, seed_site_blocks
from app.domains.cms.models import CmsPage
from app.kernel.tenancy import TENANT_MILLEGEM_ID

pytestmark = pytest.mark.ui_serverrendered


def _page(db, slug: str, *, published: bool = True, in_nav: bool = True) -> None:
    db.add(
        CmsPage(
            slug=slug,
            title=slug.title(),
            content=f"<p>{slug}</p>",
            is_published=published,
            show_in_nav=in_nav,
        )
    )


def _sitemap_paths(client) -> set[str]:
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200 and "<urlset" in resp.text
    locs = re.findall(r"<loc>([^<]+)</loc>", resp.text)
    # The first entry is always the tenant's home "/": its address is the base
    # (with a path prefix such as /raakmillegem on a platform host).
    base = locs[0][:-1]
    return {loc[len(base) :] or "/" for loc in locs}


@pytest.fixture
def site(db_session):
    seed_site_blocks(db_session, TENANT_MILLEGEM_ID, "Raak Millegem")
    _page(db_session, "over-ons")
    _page(db_session, "voorwaarden", in_nav=False)
    _page(db_session, "concept", published=False)
    db_session.commit()


def test_the_sitemap_lists_pages_and_no_blocks(client, site):
    paths = _sitemap_paths(client)

    assert {"/over-ons", "/voorwaarden", "/privacy"} <= paths, paths
    for slug in SITE_BLOCK_SLUGS:
        assert f"/{slug}" not in paths, f"the block {slug} is in the sitemap as a page"
    assert "/concept" not in paths


def test_the_sitemap_keeps_every_real_page(client, db_session, site):
    """Every published row that is not a block is listed — compared with the
    rows themselves, so a page that goes missing turns this red."""
    published = {
        f"/{p.slug}"
        for p in db_session.query(CmsPage).filter(CmsPage.is_published.is_(True)).all()
        if p.slug not in SITE_BLOCK_SLUGS
    }
    assert {"/over-ons", "/voorwaarden", "/privacy"} <= published

    assert published <= _sitemap_paths(client)


def test_a_block_has_no_address_of_its_own(client, db_session, site):
    for slug in SITE_BLOCK_SLUGS:
        assert client.get(f"/{slug}").status_code == 404, f"/{slug} answers as a page"
    assert client.get("/privacy").status_code == 200, "a real page out of the menu still answers"
    intro = (
        db_session.query(CmsPage)
        .filter(CmsPage.slug == "home-intro", CmsPage.tenant_id == TENANT_MILLEGEM_ID)
        .one()
    )
    snippet = re.sub(r"<[^>]+>", "", intro.content or "").strip()[:20]
    assert snippet and snippet in client.get("/").text, (
        "the home page no longer renders its intro block"
    )


def test_the_seed_is_the_block_list():
    """A block seeded and not listed would appear in the sitemap as a page."""
    import inspect

    from app.domains.cms import service

    assert "for slug in SITE_BLOCK_SLUGS" in inspect.getsource(service.seed_site_blocks)
