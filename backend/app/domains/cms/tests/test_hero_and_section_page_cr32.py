"""CR-32 phase 1 on the page screen and the public page: the opening of a page
(title line or hero) saved from the record screen, and a section reaching the
visitor through the editor's own save and a publish.

Broken on purpose (15 October 2026): the route not passing the hero fields →
the stored hero stays empty; `_check_opening` removed → a half-filled button is
stored instead of refused by name; `hero_view` not given to the public route's
context → the band is missing on the site.
"""

from __future__ import annotations

import json
import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.cms.models import CmsPage
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _page(db, slug: str) -> CmsPage:
    page = CmsPage(
        tenant_id=TENANT_MILLEGEM_ID,
        slug=slug,
        title="Over ons",
        content="<p>Oude tekst.</p>",
        is_published=True,
        show_in_nav=False,
    )
    db.add(page)
    db.commit()
    return page


def _login(client) -> str:
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return session


def _post(client, session, page, document=None, **fields):
    data = {
        "title": page.title,
        "slug": page.slug,
        "document": json.dumps(document or {"type": "doc", "content": []}),
        **fields,
    }
    return client.post(
        f"/admin/paginas/{page.id}",
        data=data,
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )


HERO_FIELDS = {
    "opening": "hero",
    "hero_tone": "accent",
    "hero_eyebrow": "Over ons",
    "hero_lead": "Wat wij doen.",
    "hero_b1_label": "Contact",
    "hero_b1_destination": "href",
    "hero_b1_address": "https://example.test/contact",
}


def test_the_page_screen_saves_the_hero_and_the_site_shows_it(client, db_session):
    session = _login(client)
    page = _page(db_session, "hero-scherm-cr32")
    response = _post(client, session, page, **HERO_FIELDS)
    assert response.status_code == 204, response.text[:300]
    db_session.expire_all()
    stored = db_session.get(CmsPage, page.id)
    assert stored.opening == "hero"
    assert stored.hero == {
        "tone": "accent",
        "eyebrow": "Over ons",
        "lead": "Wat wij doen.",
        "buttons": [{"label": "Contact", "href": "https://example.test/contact"}],
    }
    site = client.get("/hero-scherm-cr32").text
    main = site[site.index("<main") : site.index("</main>")]
    assert 'class="prose-hero prose-hero--accent"' in main
    assert re.findall(r"<h1[^>]*>(.*?)</h1>", main, re.S) == ["Over ons"]


def test_the_record_screen_shows_the_opening_fields_with_what_is_stored(client, db_session):
    session = _login(client)
    page = _page(db_session, "hero-velden-cr32")
    _post(client, session, page, **HERO_FIELDS)
    screen = client.get(f"/admin/paginas/{page.id}").text
    for name in ("opening", "hero_tone", "hero_eyebrow", "hero_lead", "hero_b1_label"):
        assert f'name="{name}"' in screen, name
    assert 'value="https://example.test/contact"' in screen
    assert re.search(r'<option value="hero" selected', screen)


def test_a_half_filled_button_is_refused_by_name_and_saves_nothing(client, db_session):
    session = _login(client)
    page = _page(db_session, "hero-weigering-cr32")
    response = _post(client, session, page, **{**HERO_FIELDS, "hero_b1_destination": ""})
    assert response.status_code == 200
    assert "precies één bestemming" in response.text
    db_session.expire_all()
    stored = db_session.get(CmsPage, page.id)
    assert stored.opening == "title_line" and stored.hero is None


def test_an_unknown_tone_is_refused_by_name(client, db_session):
    session = _login(client)
    page = _page(db_session, "hero-toon-cr32")
    response = _post(client, session, page, **{**HERO_FIELDS, "hero_tone": "pink"})
    assert response.status_code == 200 and "hero.tone" in response.text


def test_a_section_saved_from_the_editor_reaches_the_visitor_as_a_band(client, db_session):
    session = _login(client)
    page = _page(db_session, "sectie-cr32")
    document = {
        "type": "doc",
        "content": [
            {
                "type": "section",
                "attrs": {"tone": "tint", "eyebrow": None},
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "In de band"}]}
                ],
            }
        ],
    }
    assert _post(client, session, page, document).status_code == 204
    published = client.post(
        f"/admin/paginas/{page.id}/publiceren",
        headers={"X-CSRF-Token": csrf_token_for(session), "HX-Request": "true"},
    )
    assert published.status_code in (200, 204)
    site = client.get("/sectie-cr32").text
    assert '<div class="prose-section prose-section--tint"><p>In de band</p></div>' in site
