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
