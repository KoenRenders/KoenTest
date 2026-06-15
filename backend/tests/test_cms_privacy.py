"""Test voor de geseede privacyverklaring (#152).

Invariant: de privacypagina is publiek bereikbaar (dus gepubliceerd) en bevat de
vereiste regel over de cookieloze web-analytics. Het publieke /pages/{slug}-
endpoint serveert enkel gepubliceerde pagina's, dus een 200 bewijst publicatie.
"""


def test_privacy_page_is_published_and_mentions_analytics(client, db_session):
    resp = client.get("/api/v1/pages/privacy")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Privacyverklaring"
    assert "Umami" in (body["content"] or "")
    assert "Do-Not-Track" in (body["content"] or "")
    # Juridische pagina hoort niet in de hoofdnavigatie (#152).
    assert body["show_in_nav"] is False


def test_new_page_defaults_to_shown_in_nav(client, db_session, admin_headers):
    """Een normale nieuwe pagina staat standaard wél in de navigatie — de
    boolean vervangt de oude hardcoded slug-uitzonderingen."""
    resp = client.post(
        "/api/v1/pages",
        headers=admin_headers,
        json={"title": "Werking", "slug": "werking", "is_published": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["show_in_nav"] is True
