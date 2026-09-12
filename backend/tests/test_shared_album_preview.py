"""#881 — a shared album shows its own name and a picture.

Koen: *"How can we make sure that when we share a photo album by link (WhatsApp, Facebook)
the name and the header photo of the album travel with it?"*

`site_base.html` already set `og:type`, `og:site_name`, `og:title`, `og:description` and
`og:url`. Two things were missing and together they explain what he saw: there was **no
`og:image`** at all, so no shared link ever showed a picture, and title and description came
from the **site** rather than the page, so WhatsApp read the name of the association.

Three details decide between works and works-not, and each has a test here:

- **the full photo, not the thumbnail.** WhatsApp and Facebook reject small images or show
  them blurred; a preview wants 1200 px rather than 200. The model carries both `data` and
  `thumbnail`; this must be `data`, which is `/api/v1/media/{id}` and not `/thumb`.
- **the URL must be absolute.** A crawler does not resolve a relative path.
- **the crawler has no session.** Whatever can appear in a preview is public by definition,
  so the test fetches that image *without* a session — the way a crawler does.

Broken on purpose to check that these tests can go red: `og:image` pointed at
`f['thumb_url']` → the full-photo test falls over; the absolute prefix dropped → the
absolute-URL test falls over with a path a crawler cannot resolve; and the hardcoded
"Raak Millegem" put back in the album title → the tenant test falls over with another
association's name on the page.
"""
import pytest

from app.domains.media.models import MediaAsset

pytestmark = pytest.mark.ui_serverrendered

PLATFORM_HOST = "platform.example.test"


def _activity_with_photos(db, *, name="Zomerfeest", count=2):
    from datetime import date

    from app.domains.activities.api import Activity, ActivityDate

    activity = Activity(name=name)
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2026, 7, 1)))
    for index in range(count):
        db.add(MediaAsset(kind="activity_photo", activity_id=activity.id,
                          title=f"foto {index}", sort_order=index, is_active=True,
                          content_type="image/jpeg", byte_size=10, width=1200,
                          height=800, data=b"volledig", thumbnail=b"klein"))
    db.flush()
    return activity


def _og(html: str, prop: str) -> str | None:
    marker = f'property="{prop}" content="'
    if marker not in html:
        return None
    return html.split(marker, 1)[1].split('"', 1)[0]


def test_the_album_carries_an_absolute_og_image_a_crawler_can_fetch(client, db_session):
    """De drie eisen in één test, want ze hangen samen: volledige foto, absolute URL, en
    zonder sessie op te halen."""
    activity = _activity_with_photos(db_session)

    html = client.get(f"/activiteiten/{activity.id}/fotos").text
    image = _og(html, "og:image")

    assert image, "er is geen og:image, dus een gedeelde link toont nooit een beeld"
    assert image.startswith("http://") or image.startswith("https://"), (
        f"de URL is niet absoluut; een crawler lost dit niet op: {image}")
    assert "/thumb" not in image, (
        "de voorbeschouwing wijst naar de thumbnail; WhatsApp en Facebook wijzen kleine "
        "beelden af of tonen ze onscherp")

    # Zoals een crawler: geen sessie, en dan moet het beeld er gewoon zijn.
    client.cookies.clear()
    pad = image.split("://", 1)[1].split("/", 1)[1]
    resp = client.get(f"/{pad}")
    assert resp.status_code == 200, f"de crawler krijgt {resp.status_code} op {pad}"
    assert resp.content == b"volledig", "dit is de thumbnail en niet de volledige foto"


def test_the_og_title_is_the_album_and_not_the_site(client, db_session):
    activity = _activity_with_photos(db_session, name="Kerstmarkt")

    html = client.get(f"/activiteiten/{activity.id}/fotos").text

    titel = _og(html, "og:title")
    assert titel and "Kerstmarkt" in titel, f"og:title is {titel!r}"
    beschrijving = _og(html, "og:description")
    assert beschrijving and "Kerstmarkt" in beschrijving, (
        f"de omschrijving komt nog van de site: {beschrijving!r}")


def test_an_album_without_photos_sends_no_og_image(client, db_session):
    """Het geval dat in de praktijk het eerst voorkomt: een activiteit zonder foto's.

    Een lege of gebroken `og:image` is slechter dan geen — dan toont de voorbeschouwing
    een leeg kader.
    """
    activity = _activity_with_photos(db_session, name="Nog niets", count=0)

    html = client.get(f"/activiteiten/{activity.id}/fotos").text

    assert _og(html, "og:image") is None, "er wordt een og:image gezet zonder foto's"
    assert "twitter:card" not in html


def test_the_page_title_carries_the_tenant_name(client, db_session, monkeypatch):
    """Het tenantlek dat bij dit issue hoort: "Raak Millegem" stond hardgecodeerd in het
    titelblok van het album."""
    from app.kernel.tenant_config import set_setting

    set_setting(db_session, "display_name", "Raak Voorbeeldafdeling")
    db_session.flush()
    activity = _activity_with_photos(db_session, name="Buurtfeest")

    html = client.get(f"/activiteiten/{activity.id}/fotos").text

    titel = html.split("<title>", 1)[1].split("</title>", 1)[0]
    assert "Raak Voorbeeldafdeling" in titel, f"<title> is {titel!r}"
    assert "Raak Millegem" not in titel, (
        "de naam van een andere vereniging staat in de paginatitel")


def test_a_page_that_overrides_nothing_keeps_its_tags(client, db_session):
    """Ongewijzigd: de schil valt terug op de sitewaarden.

    Zonder deze test is "per pagina overschrijfbaar" niet te onderscheiden van "elke
    pagina heeft nu lege tags".
    """
    html = client.get("/").text

    assert _og(html, "og:title"), "de homepagina heeft geen og:title meer"
    assert _og(html, "og:description"), "de homepagina heeft geen og:description meer"
    assert _og(html, "og:image") is None, (
        "de homepagina zendt een og:image die ze niet zelf zet")
