"""Test voor de geseede privacyverklaring (#152).

Invariant: de privacypagina is publiek bereikbaar (dus gepubliceerd) en bevat de
vereiste regel over de cookieloze web-analytics. De publieke pagina toont enkel
gepubliceerde pagina's (`cms.service.get_published_page`), dus een 200 bewijst
publicatie.

Until CR-13 phase 4b (#1251) these two went through the JSON routes
`GET /api/v1/pages/{slug}` and `POST /api/v1/pages`, which had no caller and
left; they hold the same through the public page and the service the back
office's screen calls.
"""

from app.domains.cms.models import CmsPage
from app.domains.cms.service import create_page
from app.schemas.cms import CmsPageCreate


def test_privacy_page_is_published_and_mentions_analytics(client, db_session):
    resp = client.get("/privacy")
    assert resp.status_code == 200, resp.text[:200]
    assert "Privacyverklaring" in resp.text
    assert "Umami" in resp.text
    assert "Do-Not-Track" in resp.text
    # Juridische pagina hoort niet in de hoofdnavigatie (#152).
    page = db_session.query(CmsPage).filter(CmsPage.slug == "privacy").one()
    assert page.is_published is True
    assert page.show_in_nav is False


def test_new_page_defaults_to_shown_in_nav(db_session):
    """Een normale nieuwe pagina staat standaard wél in de navigatie — de
    boolean vervangt de oude hardcoded slug-uitzonderingen."""
    page = create_page(
        db_session, CmsPageCreate(title="Werking", slug="werking", is_published=True)
    )
    assert page.show_in_nav is True
