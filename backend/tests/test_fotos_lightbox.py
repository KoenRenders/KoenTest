"""#478: het publieke foto-album mag geen kapotte Alpine x-data hebben. tojson
schrijft de foto-URLs met dubbele quotes; het x-data-attribuut moet daarom met
ENKELE quotes afgebakend zijn, anders knipt de browser het attribuut af en werkt
de lightbox (klikken op een foto) niet meer."""
from app.domains.activities.api import Activity


def _activity_with_photo(db):
    from app.domains.media.api import MediaAsset

    a = Activity(name="Album")
    db.add(a)
    db.flush()
    db.add(MediaAsset(kind="activity_photo", activity_id=a.id, is_active=True,
                      data=b"\x89PNG", content_type="image/png", title="foto"))
    db.flush()
    return a


def test_album_xdata_is_single_quoted_not_broken(client, db_session):
    a = _activity_with_photo(db_session)
    db_session.commit()
    html = client.get(f"/activiteiten/{a.id}/fotos").text

    # Correct: enkel-gequote attribuut met de dubbele-quote-JSON erin.
    assert "x-data='{ open: null, urls: [" in html
    # De kapotte variant (dubbele quote binnen dubbele quote) mag NIET voorkomen.
    assert 'x-data="{ open: null, urls: ["' not in html
    # De thumbnail heeft een klik-handler die de overlay opent.
    assert '@click="open = 0"' in html


def test_album_without_photos_has_no_lightbox(client, db_session):
    a = Activity(name="Leeg album")
    db_session.add(a)
    db_session.commit()
    html = client.get(f"/activiteiten/{a.id}/fotos").text
    assert "x-data='{ open: null" not in html
    assert "Geen foto's gevonden" in html
